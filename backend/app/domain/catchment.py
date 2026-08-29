"""Catchment delineation via D8 flow routing (pysheds). Given an elevation
grid, finds a suitable pond site and delineates the catchment that drains
to it. Works on any elevation grid -- one fed from an uploaded contour
KML, one fetched live from a DEM API -- since both are reduced to the
same (array, BoundingBox) shape upstream.

Pond siting samples a spread of local flow-accumulation maxima (not just
the single global maximum) and picks the highest-ranked candidate whose
resulting catchment area actually falls in a realistic range for a small
farm/community pond. The global maximum alone tends to be wherever the
single dominant drainage line exits the analyzed area -- i.e. "the
biggest river in this map tile", not a farm pond's catchment -- which is
why it consistently claimed 20-36% of the whole surveyed area regardless
of input (observed on both the KML-upload and click-map flows).
"""

import logging
from dataclasses import dataclass
from typing import Callable

import numpy as np

# pysheds (0.5, the latest release as of writing) still calls numpy.in1d,
# which numpy removed in recent releases. np.isin is a drop-in replacement
# for the membership-test use pysheds makes of it.
if not hasattr(np, "in1d"):
    np.in1d = np.isin

from pysheds.grid import Grid
from pysheds.sview import Raster, ViewFinder
from rasterio.transform import from_bounds

from app.infrastructure.elevation_client import BoundingBox

logger = logging.getLogger(__name__)

EDGE_MARGIN_FRACTION = 0.05
METERS_PER_DEGREE_LAT = 111_320.0

# A realistic catchment scale for a small farm/community pond under Indian
# watershed-development practice -- most farm ponds serve a few hectares;
# larger community ponds/check dams might serve a few tens of hectares.
# Not the single "correct" number (no such thing without a real, sited
# survey), but a documented, literature-grounded range that keeps the
# recommendation plausible instead of claiming a third of the map tile.
MIN_CATCHMENT_AREA_M2 = 10_000  # 1 hectare
MAX_CATCHMENT_AREA_M2 = 500_000  # 50 hectares

# How many points to sample across the interior when searching for a pond
# site -- a coarse grid, not every pixel, since each candidate costs a
# real D8 catchment trace. Each sample snaps to the true local
# flow-accumulation peak within a small window around it, so the search
# isn't blind to genuine drainage features that fall between grid lines.
CANDIDATE_GRID_DIVISIONS = 20
LOCAL_WINDOW_RADIUS = 2


@dataclass(frozen=True)
class _Candidate:
    row: int
    col: int
    accumulation: float


@dataclass(frozen=True)
class CatchmentResult:
    pond_lat: float
    pond_lon: float
    catchment_area_m2: float
    catchment_cell_count: int
    flow_accumulation_at_pond: float
    catchment_boundary: list[list[float]]  # [[lon, lat], ...], closed ring


def _build_grid(elevation: np.ndarray, bbox: BoundingBox) -> tuple[Grid, Raster]:
    height, width = elevation.shape
    affine = from_bounds(bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat, width, height)
    viewfinder = ViewFinder(affine=affine, shape=elevation.shape, nodata=np.nan)
    dem = Raster(elevation.astype(np.float64), viewfinder=viewfinder)
    grid = Grid(viewfinder=viewfinder)
    return grid, dem


def _cell_area_m2(elevation: np.ndarray, bbox: BoundingBox) -> float:
    height, width = elevation.shape
    cell_width_deg = (bbox.max_lon - bbox.min_lon) / width
    cell_height_deg = (bbox.max_lat - bbox.min_lat) / height
    mean_lat_rad = np.radians((bbox.min_lat + bbox.max_lat) / 2)
    meters_per_deg_lon = METERS_PER_DEGREE_LAT * np.cos(mean_lat_rad)
    return (cell_width_deg * meters_per_deg_lon) * (cell_height_deg * METERS_PER_DEGREE_LAT)


def _mask_to_boundary_ring(mask: np.ndarray, grid: Grid) -> list[list[float]]:
    """Traces the outer boundary of the largest connected True region in
    `mask` using pysheds' polygonize, returning it as a closed [lon, lat]
    ring for map display. Falls back to the mask's bounding box if
    polygonize can't produce a usable shape (e.g. a single-cell catchment)."""
    try:
        # The DEM's viewfinder has a float NaN nodata value, which isn't
        # representable in an int32 array -- the mask needs its own
        # viewfinder with an int-compatible nodata value.
        mask_viewfinder = ViewFinder(
            affine=grid.affine, shape=mask.shape, nodata=0, crs=grid.crs
        )
        mask_raster = Raster(mask.astype(np.int32), viewfinder=mask_viewfinder)
        shapes = list(grid.polygonize(mask_raster))
        polygons = [
            geom
            for geom, value in shapes
            if value == 1 and geom.get("type") == "Polygon"
        ]
        if polygons:
            largest = max(polygons, key=lambda g: len(g["coordinates"][0]))
            return [[float(lon), float(lat)] for lon, lat in largest["coordinates"][0]]
    except Exception:
        # A traced boundary is a nice-to-have for map display, not
        # something the catchment area/pond-site result depends on --
        # log and fall through to the cruder bounding-box shape below
        # rather than failing the whole analysis over it.
        logger.warning("catchment boundary polygonize failed, falling back to bbox", exc_info=True)

    rows, cols = np.where(mask)
    if len(rows) == 0:
        return []
    affine = grid.affine
    lons_lats = [affine * (float(c), float(r)) for r, c in [(rows.min(), cols.min()), (rows.min(), cols.max()), (rows.max(), cols.max()), (rows.max(), cols.min())]]
    lons_lats.append(lons_lats[0])
    return [[lon, lat] for lon, lat in lons_lats]


def _sample_candidates(acc: np.ndarray, margin_rows: int, margin_cols: int) -> list[_Candidate]:
    height, width = acc.shape
    row_step = max(1, (height - 2 * margin_rows) // CANDIDATE_GRID_DIVISIONS)
    col_step = max(1, (width - 2 * margin_cols) // CANDIDATE_GRID_DIVISIONS)

    candidates: list[_Candidate] = []
    seen: set[tuple[int, int]] = set()
    for r in range(margin_rows, height - margin_rows, row_step):
        for c in range(margin_cols, width - margin_cols, col_step):
            r0, r1 = max(margin_rows, r - LOCAL_WINDOW_RADIUS), min(height - margin_rows, r + LOCAL_WINDOW_RADIUS + 1)
            c0, c1 = max(margin_cols, c - LOCAL_WINDOW_RADIUS), min(width - margin_cols, c + LOCAL_WINDOW_RADIUS + 1)
            window = acc[r0:r1, c0:c1]
            local_row, local_col = np.unravel_index(np.argmax(window), window.shape)
            true_row, true_col = r0 + local_row, c0 + local_col

            key = (true_row, true_col)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(_Candidate(row=true_row, col=true_col, accumulation=float(acc[true_row, true_col])))

    candidates.sort(key=lambda c: c.accumulation, reverse=True)
    return candidates


def _select_pond_site(
    candidates: list[_Candidate],
    catchment_for: Callable[[_Candidate], tuple[np.ndarray, float]],
) -> tuple[_Candidate, np.ndarray, float]:
    """Walks candidates highest-accumulation first, returning the first
    whose catchment area falls within [MIN_CATCHMENT_AREA_M2,
    MAX_CATCHMENT_AREA_M2]. Falls back to whichever candidate's area is
    closest to that range if none fit exactly, rather than failing --
    a traced catchment is still returned, it just couldn't be tuned to
    the target scale for this particular terrain."""
    if not candidates:
        raise ValueError("no candidates to select a pond site from")

    best_fallback: tuple[float, _Candidate, np.ndarray, float] | None = None
    for candidate in candidates:
        mask, area_m2 = catchment_for(candidate)
        if MIN_CATCHMENT_AREA_M2 <= area_m2 <= MAX_CATCHMENT_AREA_M2:
            return candidate, mask, area_m2

        distance = (
            MIN_CATCHMENT_AREA_M2 - area_m2 if area_m2 < MIN_CATCHMENT_AREA_M2 else area_m2 - MAX_CATCHMENT_AREA_M2
        )
        if best_fallback is None or distance < best_fallback[0]:
            best_fallback = (distance, candidate, mask, area_m2)

    logger.info("no sampled candidate's catchment fit the target area range; using the closest fallback")
    _distance, candidate, mask, area_m2 = best_fallback
    return candidate, mask, area_m2


def analyze_catchment(elevation: np.ndarray, bbox: BoundingBox) -> CatchmentResult:
    grid, dem = _build_grid(elevation, bbox)

    pit_filled = grid.fill_pits(dem)
    flooded = grid.fill_depressions(pit_filled)
    inflated = grid.resolve_flats(flooded)
    fdir = grid.flowdir(inflated, routing="d8")
    acc = np.asarray(grid.accumulation(fdir, routing="d8"))

    height, width = elevation.shape
    margin_rows = max(1, int(height * EDGE_MARGIN_FRACTION))
    margin_cols = max(1, int(width * EDGE_MARGIN_FRACTION))
    cell_area_m2 = _cell_area_m2(elevation, bbox)
    affine = grid.affine

    def catchment_for(candidate: _Candidate) -> tuple[np.ndarray, float]:
        lon, lat = affine * (candidate.col + 0.5, candidate.row + 0.5)
        mask = np.asarray(grid.catchment(x=lon, y=lat, fdir=fdir, xytype="coordinate", routing="d8"))
        return mask, float(mask.sum() * cell_area_m2)

    candidates = _sample_candidates(acc, margin_rows, margin_cols)
    candidate, catchment_mask, area_m2 = _select_pond_site(candidates, catchment_for)

    pond_lon, pond_lat = affine * (candidate.col + 0.5, candidate.row + 0.5)
    cell_count = int(catchment_mask.sum())
    boundary = _mask_to_boundary_ring(catchment_mask, grid)

    return CatchmentResult(
        pond_lat=float(pond_lat),
        pond_lon=float(pond_lon),
        catchment_area_m2=area_m2,
        catchment_cell_count=cell_count,
        flow_accumulation_at_pond=candidate.accumulation,
        catchment_boundary=boundary,
    )

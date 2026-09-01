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
from dataclasses import dataclass, replace
from typing import Callable

import numpy as np
from scipy import ndimage

# pysheds (0.5, the latest release as of writing) still calls numpy.in1d,
# which numpy removed in recent releases. np.isin is a drop-in replacement
# for the membership-test use pysheds makes of it.
if not hasattr(np, "in1d"):
    np.in1d = np.isin

from pysheds.grid import Grid
from pysheds.sview import Raster, ViewFinder
from rasterio.transform import from_bounds

from app.domain.pond import CANDIDATE_DEPTHS_M
from app.infrastructure.elevation_client import BoundingBox

logger = logging.getLogger(__name__)

EDGE_MARGIN_FRACTION = 0.05
METERS_PER_DEGREE_LAT = 111_320.0

# The catchment scale this app deliberately targets: a farm pond under
# Indian watershed-development practice, which serves a few hectares.
#
# This band used to run to 50 hectares, which spans two different
# interventions -- a farm pond (a dug excavation) and a check dam or
# percolation tank (a bund across a drainage line, serving tens of
# hectares). At the top of that range the analysis correctly returned a
# check-dam-scale structure, which then read as an absurd "pond": a
# 26 ha catchment produced a 250m-square recommendation. Narrowing the
# band makes site selection look for sites at the scale this app
# actually models. The trade-off is accepted and real: the app no longer
# recommends check-dam or percolation-tank scale structures at all.
# See docs/DECISIONS.md D-010.
MIN_CATCHMENT_AREA_M2 = 10_000  # 1 hectare
MAX_CATCHMENT_AREA_M2 = 50_000  # 5 hectares

# How many points to sample across the interior when searching for a pond
# site -- a coarse grid, not every pixel, since each candidate costs a
# real D8 catchment trace. Each sample snaps to the true local
# flow-accumulation peak within a small window around it, so the search
# isn't blind to genuine drainage features that fall between grid lines.
CANDIDATE_GRID_DIVISIONS = 20
LOCAL_WINDOW_RADIUS = 2

FLOOD_STEP_COUNT = 40  # resolution of the flood-fill volume integration


@dataclass(frozen=True)
class _Candidate:
    row: int
    col: int
    accumulation: float
    is_depression: bool = False


@dataclass(frozen=True)
class CatchmentResult:
    pond_lat: float
    pond_lon: float
    catchment_area_m2: float
    catchment_cell_count: int
    flow_accumulation_at_pond: float
    catchment_boundary: list[list[float]]  # [[lon, lat], ...], closed ring
    achievable_volume_m3_by_depth: dict[float, float]


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


def _find_depressions(
    elevation: np.ndarray, margin_rows: int, margin_cols: int, valid_mask: np.ndarray | None = None
) -> np.ndarray:
    """True where a cell has no neighbor (of its 8 neighbors) that's
    strictly lower -- a local low point on the RAW, unconditioned
    elevation grid. Must run on this raw grid, not the pit-filled one:
    pysheds' fill_pits/fill_depressions/resolve_flats exist specifically
    to eliminate these for flow routing, so by the time accumulation is
    computed in analyze_catchment, real depressions are already gone
    from that grid.

    `valid_mask`, when given, restricts depressions to cells where it's
    True -- used to exclude nearest-neighbor-extrapolated filler (e.g.
    kml_parser.py's fallback for gaps outside a KML's surveyed convex
    hull) from ever being treated as a real depression. A large flat
    interpolation artifact is otherwise indistinguishable from a genuine
    flat-bottomed basin by elevation values alone, and can be large
    enough to swallow an entire catchment -- see docs/DECISIONS.md."""
    local_min = ndimage.minimum_filter(elevation, size=3, mode="nearest")
    is_depression = elevation <= local_min

    is_depression[:margin_rows, :] = False
    is_depression[elevation.shape[0] - margin_rows :, :] = False
    is_depression[:, :margin_cols] = False
    is_depression[:, elevation.shape[1] - margin_cols :] = False

    if valid_mask is not None:
        is_depression &= valid_mask

    return is_depression


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
    """Walks candidates highest-accumulation first, preferring a real
    depression (see _find_depressions) over a non-depression candidate
    whenever one fits the target area range -- a depression is where
    water naturally pools, a more physically grounded pond site than an
    arbitrary point on the accumulation-ranked list. Falls back to the
    best-fitting candidate overall (depression or not) if no depression
    candidate fits, then to whichever candidate's area is closest to the
    target range if nothing fits at all, rather than failing -- a traced
    catchment is still returned, it just couldn't be tuned to the target
    scale or a natural depression for this particular terrain.

    Each candidate's (expensive, real) catchment trace is memoized by
    position, so checking the depression subset first and then
    potentially the full list never re-traces the same candidate twice.
    """
    if not candidates:
        raise ValueError("no candidates to select a pond site from")

    cache: dict[tuple[int, int], tuple[np.ndarray, float]] = {}

    def traced(candidate: _Candidate) -> tuple[np.ndarray, float]:
        key = (candidate.row, candidate.col)
        if key not in cache:
            cache[key] = catchment_for(candidate)
        return cache[key]

    def first_in_range(pool: list[_Candidate]) -> tuple[_Candidate, np.ndarray, float] | None:
        for candidate in pool:
            mask, area_m2 = traced(candidate)
            if MIN_CATCHMENT_AREA_M2 <= area_m2 <= MAX_CATCHMENT_AREA_M2:
                return candidate, mask, area_m2
        return None

    depression_candidates = [c for c in candidates if c.is_depression]
    if depression_candidates:
        found = first_in_range(depression_candidates)
        if found is not None:
            return found

    found = first_in_range(candidates)
    if found is not None:
        return found

    best_fallback: tuple[float, _Candidate, np.ndarray, float] | None = None
    for candidate in candidates:
        mask, area_m2 = traced(candidate)
        distance = (
            MIN_CATCHMENT_AREA_M2 - area_m2 if area_m2 < MIN_CATCHMENT_AREA_M2 else area_m2 - MAX_CATCHMENT_AREA_M2
        )
        if best_fallback is None or distance < best_fallback[0]:
            best_fallback = (distance, candidate, mask, area_m2)

    _distance, candidate, mask, area_m2 = best_fallback
    logger.warning(
        "no sampled candidate's catchment fit the target area range "
        "(%d-%d m^2); using the closest fallback, area=%.1f m^2",
        MIN_CATCHMENT_AREA_M2,
        MAX_CATCHMENT_AREA_M2,
        area_m2,
    )
    return candidate, mask, area_m2


def _flood_fill_achievable_volume(
    elevation: np.ndarray,
    cell_area_m2: float,
    site_row: int,
    site_col: int,
    catchment_mask: np.ndarray,
    depths_m: tuple[float, ...],
) -> dict[float, float]:
    """For the chosen pond site, raises a flood level step by step from the
    site's own base elevation (on the RAW, unconditioned grid -- the same
    reason _find_depressions doesn't use the pit-filled grid) and
    integrates flooded-area-vs-elevation (trapezoidal) into an achievable
    volume at each of `depths_m` metres above that base. The flood is
    constrained to the site's own traced catchment and stops early if it
    would spill past that catchment's extent or the raster's edge -- once
    that happens, every deeper depth gets the same capped volume, since
    the terrain physically can't hold more without an embankment higher
    than its own natural rim.
    """
    base_elevation = float(elevation[site_row, site_col])
    max_depth = max(depths_m)
    step = max_depth / FLOOD_STEP_COUNT

    prev_area_m2 = 0.0
    prev_level = base_elevation
    volume_m3 = 0.0
    volume_at_depth: dict[float, float] = {}
    remaining = sorted(depths_m)
    spilled = False

    for i in range(FLOOD_STEP_COUNT + 1):
        level = base_elevation + min(i * step, max_depth)
        if not spilled:
            flooded = (elevation <= level) & catchment_mask
            labeled, _ = ndimage.label(flooded, structure=np.ones((3, 3)))
            site_label = labeled[site_row, site_col]
            region = (labeled == site_label) if site_label != 0 else np.zeros_like(flooded)
            touches_edge = (
                region[0, :].any() or region[-1, :].any() or region[:, 0].any() or region[:, -1].any()
            )
            spilled = touches_edge or region.sum() >= catchment_mask.sum()
            area_m2 = float(region.sum()) * cell_area_m2
            volume_m3 += (prev_area_m2 + area_m2) / 2.0 * (level - prev_level)
            prev_area_m2, prev_level = area_m2, level

        depth_here = level - base_elevation
        while remaining and depth_here >= remaining[0] - 1e-9:
            volume_at_depth[remaining.pop(0)] = volume_m3

    for depth in remaining:
        volume_at_depth[depth] = volume_m3
    return volume_at_depth


def analyze_catchment(
    elevation: np.ndarray, bbox: BoundingBox, valid_mask: np.ndarray | None = None
) -> CatchmentResult:
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
        # Address the outlet by grid index, not by geographic coordinate.
        # pysheds' coordinate path snaps to a cell *corner* by default
        # (its `snap='corner'`), so handing it a cell *centre* lands the
        # trace on a neighbouring cell -- the returned catchment then
        # belongs to a different cell than the candidate, and frequently
        # doesn't even contain it. Everything anchored at the candidate
        # afterwards (the flood-fill's achievable volume, the reported
        # pond location, the reported flow accumulation) was then
        # describing a different place than the mask. Indices remove the
        # round-trip entirely: the trace starts exactly where we mean.
        mask = np.asarray(
            grid.catchment(x=candidate.col, y=candidate.row, fdir=fdir, xytype="index", routing="d8")
        )
        return mask, float(mask.sum() * cell_area_m2)

    candidates = _sample_candidates(acc, margin_rows, margin_cols)
    depression_mask = _find_depressions(elevation, margin_rows, margin_cols, valid_mask)
    candidates = [replace(c, is_depression=bool(depression_mask[c.row, c.col])) for c in candidates]
    candidate, catchment_mask, area_m2 = _select_pond_site(candidates, catchment_for)

    pond_lon, pond_lat = affine * (candidate.col + 0.5, candidate.row + 0.5)
    cell_count = int(catchment_mask.sum())
    boundary = _mask_to_boundary_ring(catchment_mask, grid)
    achievable_volume = _flood_fill_achievable_volume(
        elevation, cell_area_m2, candidate.row, candidate.col, catchment_mask, CANDIDATE_DEPTHS_M
    )

    return CatchmentResult(
        pond_lat=float(pond_lat),
        pond_lon=float(pond_lon),
        catchment_area_m2=area_m2,
        catchment_cell_count=cell_count,
        flow_accumulation_at_pond=candidate.accumulation,
        catchment_boundary=boundary,
        achievable_volume_m3_by_depth=achievable_volume,
    )

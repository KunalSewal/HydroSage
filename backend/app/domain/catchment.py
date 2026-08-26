"""Catchment delineation via D8 flow routing (pysheds). Given an elevation
grid, finds a suitable pond site (the point with the highest flow
accumulation, away from the raster edge to avoid boundary artifacts) and
delineates the catchment that drains to it. Works on any elevation grid --
one fed from an uploaded contour KML, one fetched live from a DEM API --
since both are reduced to the same (array, BoundingBox) shape upstream.
"""

import logging
from dataclasses import dataclass

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
    interior = acc[margin_rows : height - margin_rows, margin_cols : width - margin_cols]
    local_row, local_col = np.unravel_index(np.argmax(interior), interior.shape)
    row, col = local_row + margin_rows, local_col + margin_cols

    affine = grid.affine
    pond_lon, pond_lat = affine * (col + 0.5, row + 0.5)

    catchment_mask = np.asarray(
        grid.catchment(x=pond_lon, y=pond_lat, fdir=fdir, xytype="coordinate", routing="d8")
    )
    cell_count = int(catchment_mask.sum())
    area_m2 = cell_count * _cell_area_m2(elevation, bbox)
    boundary = _mask_to_boundary_ring(catchment_mask, grid)

    return CatchmentResult(
        pond_lat=float(pond_lat),
        pond_lon=float(pond_lon),
        catchment_area_m2=float(area_m2),
        catchment_cell_count=cell_count,
        flow_accumulation_at_pond=float(acc[row, col]),
        catchment_boundary=boundary,
    )

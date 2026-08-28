"""Contour generation from an elevation raster. Pure function: no I/O, no
FastAPI/DB imports — testable in isolation, per docs/ARCHITECTURE.md."""

import math

import numpy as np
from skimage import measure

from app.infrastructure.elevation_client import BoundingBox

_TARGET_LEVEL_COUNT = 8
_NICE_MULTIPLES = (1, 2, 5, 10)


def _nice_interval(z_min: float, z_max: float, target_levels: int = _TARGET_LEVEL_COUNT) -> float:
    """Pick a round-number contour interval (1/2/5/10 x a power of ten) that
    yields roughly `target_levels` bands across [z_min, z_max] — the same
    approach real topo maps use, instead of a fixed level count that looks
    either cluttered (steep terrain) or empty (flat terrain)."""
    span = z_max - z_min
    if span <= 0:
        return 1.0
    raw_step = span / target_levels
    magnitude = 10 ** math.floor(math.log10(raw_step))
    for multiple in _NICE_MULTIPLES:
        step = multiple * magnitude
        if step >= raw_step:
            return step
    return _NICE_MULTIPLES[-1] * magnitude


def generate_contours(
    elevation: np.ndarray, bbox: BoundingBox, interval: float | None = None
) -> list[dict]:
    """Generate contour lines from an elevation grid, in lon/lat coordinates.

    `bbox` must be the area actually covered by `elevation` (e.g. the
    `covered` bbox returned by ElevationClient.get_dem_for_bbox — DEM-tile
    mosaics are snapped to tile edges, so this is usually not exactly the
    bbox that was originally requested).

    `interval` is the elevation gap (in the same units as `elevation`,
    normally metres) between adjacent contour lines. When omitted, a round
    interval is picked automatically via `_nice_interval`.
    """
    z_min, z_max = float(elevation.min()), float(elevation.max())
    if z_min == z_max:
        return []

    step = interval if interval is not None else _nice_interval(z_min, z_max)
    first_level = math.ceil(z_min / step) * step
    levels = np.arange(first_level, z_max, step)
    if levels.size == 0:
        levels = np.array([(z_min + z_max) / 2])
    height, width = elevation.shape

    def to_lonlat(row: float, col: float) -> list[float]:
        lon = bbox.min_lon + (col / (width - 1)) * (bbox.max_lon - bbox.min_lon)
        lat = bbox.max_lat - (row / (height - 1)) * (bbox.max_lat - bbox.min_lat)
        return [lon, lat]

    contours = []
    for level in levels:
        for line in measure.find_contours(elevation, level=float(level)):
            contours.append(
                {
                    "elevation": float(level),
                    "coordinates": [to_lonlat(row, col) for row, col in line],
                }
            )
    return contours

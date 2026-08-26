"""Contour generation from an elevation raster. Pure function: no I/O, no
FastAPI/DB imports — testable in isolation, per docs/ARCHITECTURE.md."""

import numpy as np
from skimage import measure

from app.infrastructure.elevation_client import BoundingBox


def generate_contours(
    elevation: np.ndarray, bbox: BoundingBox, num_levels: int = 10
) -> list[dict]:
    """Generate contour lines from an elevation grid, in lon/lat coordinates.

    `bbox` must be the area actually covered by `elevation` (e.g. the
    `covered` bbox returned by ElevationClient.get_dem_for_bbox — DEM-tile
    mosaics are snapped to tile edges, so this is usually not exactly the
    bbox that was originally requested).
    """
    z_min, z_max = float(elevation.min()), float(elevation.max())
    if z_min == z_max:
        return []

    levels = np.linspace(z_min, z_max, num_levels + 2)[1:-1]
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

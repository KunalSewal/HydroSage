"""Geometry for a land area the user draws on the map. Pure functions: no
I/O, testable in isolation, per docs/ARCHITECTURE.md.

A drawn area is where the pond may go, not the whole analysis extent.
Water reaching a site inside the area can come from uphill land outside
it, so the elevation grid is fetched for a padded bbox around the polygon
(`analysis_bbox_for`) and only the pond *site* search is limited to the
polygon (`rasterize_polygon` -> analyze_catchment's `site_mask`). Cutting
the grid off at the polygon edge would truncate those catchments. See
docs/DECISIONS.md D-013.
"""

import math

import numpy as np
from rasterio.features import rasterize
from rasterio.transform import from_bounds

from app.infrastructure.elevation_client import BoundingBox

METERS_PER_DEGREE_LAT = 111_320.0

# A catchment in the target range (domain/catchment.py: 1-5 ha) needs at
# least that much room to be sited, so anything smaller can't be answered.
MIN_AREA_M2 = 10_000  # 1 hectare

# Caps the polygon's extent on either axis at the same ~6.6 km the
# click-a-point flow analyzes. The limit is memory: each deployed API
# instance runs in a 512 MB container (D-012), and the padded grid for a
# 0.06 deg polygon is about 324 x 324 cells at the DEM's 30 m, close to the
# 300 x 300 grid the KML path was measured to fit.
MAX_SPAN_DEG = 0.06
# Absorbs floating-point error when a shape is drawn exactly at the limit.
_SPAN_TOLERANCE_DEG = 1e-9

# Padding for upstream land outside the polygon: a quarter of the
# polygon's span on each side, but never less than ~550 m, so a small area
# still sees the slope above it.
PAD_FRACTION = 0.25
MIN_PAD_DEG = 0.005


def _open_ring(ring: list[list[float]]) -> list[list[float]]:
    """Drops an explicit closing point (first == last) if present."""
    if len(ring) > 1 and ring[0] == ring[-1]:
        return ring[:-1]
    return ring


def polygon_area_m2(ring: list[list[float]]) -> float:
    """Shoelace area of a [lon, lat] ring on a local equirectangular
    projection. Accurate to well under 1% at the few-km scale MAX_SPAN_DEG
    allows, and needs no projection library."""
    points = _open_ring(ring)
    mean_lat = math.radians(sum(lat for _, lat in points) / len(points))
    meters_per_deg_lon = METERS_PER_DEGREE_LAT * math.cos(mean_lat)
    xs = [lon * meters_per_deg_lon for lon, _ in points]
    ys = [lat * METERS_PER_DEGREE_LAT for _, lat in points]
    twice_area = sum(xs[i] * ys[(i + 1) % len(xs)] - xs[(i + 1) % len(xs)] * ys[i] for i in range(len(xs)))
    return abs(twice_area) / 2


def validate_area(ring: list[list[float]]) -> None:
    """Raises ValueError, with a message fit to show the user, if `ring`
    can't be analyzed."""
    points = _open_ring(ring)
    if len(points) < 3:
        raise ValueError("an area needs at least 3 points")
    if any(len(p) < 2 or not (-180 <= p[0] <= 180 and -90 <= p[1] <= 90) for p in points):
        raise ValueError("coordinates must be [lon, lat] within valid ranges")

    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    if max(lons) - min(lons) > MAX_SPAN_DEG + _SPAN_TOLERANCE_DEG or max(lats) - min(lats) > MAX_SPAN_DEG + _SPAN_TOLERANCE_DEG:
        km = MAX_SPAN_DEG * METERS_PER_DEGREE_LAT / 1000
        raise ValueError(f"area is too large: keep it within about {km:.1f} km on each side")

    area = polygon_area_m2(points)
    if area < MIN_AREA_M2:
        raise ValueError(
            f"area is too small ({area / 10_000:.2f} ha): draw at least {MIN_AREA_M2 / 10_000:.0f} ha"
        )


def analysis_bbox_for(ring: list[list[float]]) -> BoundingBox:
    points = _open_ring(ring)
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    pad_lon = max(MIN_PAD_DEG, (max(lons) - min(lons)) * PAD_FRACTION)
    pad_lat = max(MIN_PAD_DEG, (max(lats) - min(lats)) * PAD_FRACTION)
    return BoundingBox(
        min_lon=min(lons) - pad_lon,
        min_lat=min(lats) - pad_lat,
        max_lon=max(lons) + pad_lon,
        max_lat=max(lats) + pad_lat,
    )


def rasterize_polygon(ring: list[list[float]], bbox: BoundingBox, shape: tuple[int, int]) -> np.ndarray:
    """Boolean mask, True for grid cells whose centre lies inside `ring`.

    Uses the same bounds-to-affine mapping as domain/catchment.py's
    _build_grid (row 0 = north), so mask[row, col] lines up with the
    elevation cell the catchment analysis sees at [row, col]."""
    height, width = shape
    transform = from_bounds(bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat, width, height)
    geometry = {"type": "Polygon", "coordinates": [[tuple(p[:2]) for p in _open_ring(ring)] + [tuple(ring[0][:2])]]}
    burned = rasterize([(geometry, 1)], out_shape=shape, transform=transform, fill=0, dtype="uint8")
    return burned.astype(bool)

"""Parses a contour-line KML (elevation contour lines as LineString
Placemarks) into an interpolated elevation grid, matching the shape
ElevationClient.get_dem_for_bbox produces, so the same catchment analysis
can run on either input.
"""

import xml.etree.ElementTree as ET

import numpy as np
from scipy.interpolate import griddata

from app.infrastructure.elevation_client import BoundingBox

_KML_NS_URI = "http://www.opengis.net/kml/2.2"
_KML_NS = {"kml": _KML_NS_URI}
DEFAULT_GRID_SIZE = 300


def _extract_contour_points(kml_bytes: bytes) -> list[tuple[float, float, float]]:
    root = ET.fromstring(kml_bytes)
    points: list[tuple[float, float, float]] = []

    for placemark in root.iter(f"{{{_KML_NS_URI}}}Placemark"):
        name_elem = placemark.find("kml:name", _KML_NS)
        if name_elem is None or name_elem.text is None:
            continue
        try:
            elevation = float(name_elem.text)
        except ValueError:
            continue

        coords_elem = placemark.find(".//kml:LineString/kml:coordinates", _KML_NS)
        if coords_elem is None or coords_elem.text is None:
            continue

        for vertex in coords_elem.text.split():
            parts = vertex.split(",")
            if len(parts) < 2:
                continue
            lon, lat = float(parts[0]), float(parts[1])
            points.append((lon, lat, elevation))

    return points


def parse_contour_kml(
    kml_bytes: bytes, grid_size: int = DEFAULT_GRID_SIZE
) -> tuple[np.ndarray, BoundingBox]:
    points = _extract_contour_points(kml_bytes)
    if len(points) < 3:
        raise ValueError("KML has too few contour points to interpolate a surface")

    lons = np.array([p[0] for p in points])
    lats = np.array([p[1] for p in points])
    elevations = np.array([p[2] for p in points])

    bbox = BoundingBox(
        min_lon=float(lons.min()),
        min_lat=float(lats.min()),
        max_lon=float(lons.max()),
        max_lat=float(lats.max()),
    )

    grid_lon = np.linspace(bbox.min_lon, bbox.max_lon, grid_size)
    grid_lat = np.linspace(bbox.max_lat, bbox.min_lat, grid_size)  # row 0 = north
    mesh_lon, mesh_lat = np.meshgrid(grid_lon, grid_lat)

    elevation_grid = griddata((lons, lats), elevations, (mesh_lon, mesh_lat), method="linear")

    # Linear interpolation leaves NaN outside the convex hull of the input
    # points; fill those with nearest-neighbor so the grid has no gaps.
    nan_mask = np.isnan(elevation_grid)
    if nan_mask.any():
        nearest = griddata((lons, lats), elevations, (mesh_lon, mesh_lat), method="nearest")
        elevation_grid[nan_mask] = nearest[nan_mask]

    return elevation_grid, bbox

"""Parses a contour-line KML/KMZ (elevation contour lines as LineString
Placemarks) into both an interpolated elevation grid, matching the shape
ElevationClient.get_dem_for_bbox produces (so the same catchment analysis
can run on either input), and the original parsed line geometry, kept
separately so callers can display the KML's own precision instead of the
grid's lossy marching-squares re-trace (see analyze_contour.py).
"""

import io
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import griddata

from app.infrastructure.elevation_client import BoundingBox

_KML_NS_URI = "http://www.opengis.net/kml/2.2"
_KML_NS = {"kml": _KML_NS_URI}
DEFAULT_GRID_SIZE = 300


@dataclass(frozen=True)
class ContourLine:
    elevation: float
    points: list[tuple[float, float]]  # [(lon, lat), ...], in KML order


def _load_kml_bytes(raw: bytes) -> bytes:
    """Returns raw KML bytes, unzipping the first .kml entry if `raw` is a
    KMZ (a zip archive) rather than raw KML XML. Prefers an entry literally
    named doc.kml if present, matching common KMZ export conventions."""
    if raw[:2] != b"PK":
        return raw
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            kml_names = [name for name in archive.namelist() if name.lower().endswith(".kml")]
            if not kml_names:
                raise ValueError("KMZ archive does not contain a .kml file")
            kml_names.sort(key=lambda name: (name.lower() != "doc.kml", name))
            return archive.read(kml_names[0])
    except zipfile.BadZipFile as error:
        raise ValueError("file looks like a KMZ but is not a valid zip archive") from error


def _extract_contour_lines(kml_bytes: bytes) -> list[ContourLine]:
    root = ET.fromstring(kml_bytes)
    lines: list[ContourLine] = []

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

        points: list[tuple[float, float]] = []
        for vertex in coords_elem.text.split():
            parts = vertex.split(",")
            if len(parts) < 2:
                continue
            lon, lat = float(parts[0]), float(parts[1])
            points.append((lon, lat))

        if len(points) >= 2:
            lines.append(ContourLine(elevation=elevation, points=points))

    return lines


def parse_contour_kml(
    kml_bytes: bytes, grid_size: int = DEFAULT_GRID_SIZE
) -> tuple[np.ndarray, BoundingBox, list[ContourLine]]:
    kml_bytes = _load_kml_bytes(kml_bytes)
    lines = _extract_contour_lines(kml_bytes)

    points = [(lon, lat, line.elevation) for line in lines for lon, lat in line.points]
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

    return elevation_grid, bbox, lines

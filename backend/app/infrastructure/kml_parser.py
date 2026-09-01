"""Parses a contour-line KML/KMZ (elevation contour lines as LineString
Placemarks) into an interpolated elevation grid, matching the shape
ElevationClient.get_dem_for_bbox produces (so the same catchment analysis
can run on either input); the original parsed line geometry, kept
separately so callers can display the KML's own precision instead of the
grid's lossy marching-squares re-trace (see analyze_contour.py); and a
valid_mask marking which grid cells are genuinely interpolated from
surveyed data vs. nearest-neighbor filler for gaps outside the KML's own
coverage -- passed on to domain/catchment.py so extrapolated filler is
never mistaken for a real depression (see docs/DECISIONS.md).
"""

import io
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import griddata
from scipy.spatial import cKDTree

from app.infrastructure.elevation_client import BoundingBox

_KML_NS_URI = "http://www.opengis.net/kml/2.2"
_KML_NS = {"kml": _KML_NS_URI}
DEFAULT_GRID_SIZE = 300
# A KMZ's compressed size can be a poor proxy for how much memory unzipping
# it will actually use -- ordinary DEFLATE can amplify a modest upload by
# roughly 1000x. ZipInfo.file_size (read from the archive's own metadata,
# without decompressing anything) is checked against this cap before the
# entry is read into memory, so a crafted or accidental zip bomb fails
# cleanly with a 422 instead of exhausting server memory. 200 MiB
# comfortably covers any realistic contour-map KML while still bounding
# the worst case.
MAX_KMZ_ENTRY_SIZE_BYTES = 200 * 1024 * 1024


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
            chosen = kml_names[0]
            entry_size = archive.getinfo(chosen).file_size
            if entry_size > MAX_KMZ_ENTRY_SIZE_BYTES:
                raise ValueError(
                    f"KMZ entry '{chosen}' is too large ({entry_size} bytes uncompressed, "
                    f"limit is {MAX_KMZ_ENTRY_SIZE_BYTES} bytes)"
                )
            return archive.read(chosen)
    except zipfile.BadZipFile as error:
        raise ValueError("file looks like a KMZ but is not a valid zip archive") from error


def _extract_contour_lines(kml_bytes: bytes) -> list[ContourLine]:
    """Streams the document rather than building a whole ElementTree.

    A survey KML is mostly coordinate text -- the sample file expands from
    6.7 MB on disk to roughly 130 MB as a parsed tree, which matters because
    the analysis runs inside a 512 MB container (see docs/DECISIONS.md
    D-012). Clearing each Placemark once it has been read keeps only the
    extracted lines in memory. Output is identical to the tree-based parse.
    """
    lines: list[ContourLine] = []

    for _event, placemark in ET.iterparse(io.BytesIO(kml_bytes), events=("end",)):
        if placemark.tag != f"{{{_KML_NS_URI}}}Placemark":
            continue

        name_elem = placemark.find("kml:name", _KML_NS)
        coords_elem = placemark.find(".//kml:LineString/kml:coordinates", _KML_NS)

        if name_elem is not None and name_elem.text is not None and coords_elem is not None and coords_elem.text is not None:
            try:
                elevation = float(name_elem.text)
            except ValueError:
                placemark.clear()
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

        # Release the parsed element; without this iterparse still accumulates
        # the full tree and saves nothing.
        placemark.clear()

    return lines


def parse_contour_kml(
    kml_bytes: bytes, grid_size: int = DEFAULT_GRID_SIZE
) -> tuple[np.ndarray, BoundingBox, list[ContourLine], np.ndarray]:
    kml_bytes = _load_kml_bytes(kml_bytes)
    lines = _extract_contour_lines(kml_bytes)

    total_points = sum(len(line.points) for line in lines)
    if total_points < 3:
        raise ValueError("KML has too few contour points to interpolate a surface")

    # Filled column-wise straight from `lines` rather than via an intermediate
    # list of ~160k Python tuples, which for the sample file is ~20 MB that
    # would still be alive during the interpolation below -- the peak this
    # whole function is budgeted against (docs/DECISIONS.md D-012).
    lons = np.empty(total_points, dtype=np.float64)
    lats = np.empty(total_points, dtype=np.float64)
    elevations = np.empty(total_points, dtype=np.float64)
    offset = 0
    for line in lines:
        count = len(line.points)
        lons[offset : offset + count] = [lon for lon, _ in line.points]
        lats[offset : offset + count] = [lat for _, lat in line.points]
        elevations[offset : offset + count] = line.elevation
        offset += count

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
    # valid_mask records which cells came from genuine linear interpolation
    # (True) vs. this nearest-neighbor fallback (False) -- callers use it to
    # avoid treating extrapolated filler as real terrain (see
    # domain/catchment.py's analyze_catchment valid_mask parameter).
    nan_mask = np.isnan(elevation_grid)
    valid_mask = ~nan_mask
    if nan_mask.any():
        # Queried only for the cells that are actually NaN -- a small fraction
        # of the grid (2,744 of 90,000 for the sample file). griddata's own
        # "nearest" method would build the same tree but evaluate all 90,000
        # cells and discard almost every result. Values are identical.
        tree = cKDTree(np.column_stack([lons, lats]))
        _distances, indices = tree.query(np.column_stack([mesh_lon[nan_mask], mesh_lat[nan_mask]]))
        elevation_grid[nan_mask] = elevations[indices]

    return elevation_grid, bbox, lines, valid_mask

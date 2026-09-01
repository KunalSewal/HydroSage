import io
import zipfile

import pytest

from app.infrastructure.kml_parser import (
    MAX_KMZ_ENTRY_SIZE_BYTES,
    ContourLine,
    parse_contour_kml,
)

_SAMPLE_KML = b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>250</name>
      <LineString>
        <coordinates>74.60,19.06,0 74.61,19.06,0 74.61,19.07,0</coordinates>
      </LineString>
    </Placemark>
    <Placemark>
      <name>260</name>
      <LineString>
        <coordinates>74.60,19.08,0 74.61,19.08,0 74.61,19.09,0</coordinates>
      </LineString>
    </Placemark>
    <Placemark>
      <name>270</name>
      <LineString>
        <coordinates>74.60,19.10,0 74.61,19.10,0 74.61,19.11,0</coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>
"""


def _as_kmz(kml_bytes: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("doc.kml", kml_bytes)
    return buffer.getvalue()


def test_parse_contour_kml_returns_the_original_line_geometry():
    _elevation, _bbox, lines, _valid_mask = parse_contour_kml(_SAMPLE_KML)

    assert lines == [
        ContourLine(elevation=250.0, points=[(74.60, 19.06), (74.61, 19.06), (74.61, 19.07)]),
        ContourLine(elevation=260.0, points=[(74.60, 19.08), (74.61, 19.08), (74.61, 19.09)]),
        ContourLine(elevation=270.0, points=[(74.60, 19.10), (74.61, 19.10), (74.61, 19.11)]),
    ]


def test_parse_contour_kml_still_produces_an_interpolated_grid():
    elevation, bbox, _lines, _valid_mask = parse_contour_kml(_SAMPLE_KML, grid_size=20)

    assert elevation.shape == (20, 20)
    assert bbox.min_lon == pytest.approx(74.60)
    assert bbox.max_lat == pytest.approx(19.11)


def test_parse_contour_kml_accepts_a_kmz_archive():
    kmz_bytes = _as_kmz(_SAMPLE_KML)

    _elevation, _bbox, lines, _valid_mask = parse_contour_kml(kmz_bytes)

    assert len(lines) == 3
    assert lines[0].elevation == 250.0


def test_parse_contour_kml_rejects_a_kmz_with_no_kml_inside():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "not a kml file")

    with pytest.raises(ValueError, match="kml"):
        parse_contour_kml(buffer.getvalue())


def test_parse_contour_kml_rejects_a_corrupted_zip_looking_file():
    corrupted = b"PK" + b"not actually a valid zip archive"

    with pytest.raises(ValueError, match="zip"):
        parse_contour_kml(corrupted)


def test_parse_contour_kml_rejects_a_kmz_entry_that_declares_an_oversized_uncompressed_size(
    monkeypatch,
):
    """When a KMZ entry's declared uncompressed size exceeds the cap, reject it."""
    import app.infrastructure.kml_parser as kml_parser_module

    monkeypatch.setattr(kml_parser_module, "MAX_KMZ_ENTRY_SIZE_BYTES", 10)
    kmz_bytes = _as_kmz(_SAMPLE_KML)

    with pytest.raises(ValueError, match="too large"):
        parse_contour_kml(kmz_bytes)


def test_parse_contour_kml_returns_a_valid_mask_matching_the_grid_shape():
    elevation, _bbox, _lines, valid_mask = parse_contour_kml(_SAMPLE_KML, grid_size=20)

    assert valid_mask.shape == elevation.shape
    assert valid_mask.dtype == bool


def test_parse_contour_kml_valid_mask_is_false_outside_the_surveyed_convex_hull():
    # The 3 sample lines all span the same narrow longitude band; the grid's
    # bounding box corners at the extreme latitude rows fall well outside
    # the triangulated convex hull of the input points, so at least one
    # cell must be marked as nearest-neighbor-filled (not genuinely
    # interpolated) rather than every cell being trivially True.
    _elevation, _bbox, _lines, valid_mask = parse_contour_kml(_SAMPLE_KML, grid_size=20)

    assert not valid_mask.all()

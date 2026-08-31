import io
import zipfile

import pytest

from app.infrastructure.kml_parser import ContourLine, parse_contour_kml

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
    _elevation, _bbox, lines = parse_contour_kml(_SAMPLE_KML)

    assert lines == [
        ContourLine(elevation=250.0, points=[(74.60, 19.06), (74.61, 19.06), (74.61, 19.07)]),
        ContourLine(elevation=260.0, points=[(74.60, 19.08), (74.61, 19.08), (74.61, 19.09)]),
        ContourLine(elevation=270.0, points=[(74.60, 19.10), (74.61, 19.10), (74.61, 19.11)]),
    ]


def test_parse_contour_kml_still_produces_an_interpolated_grid():
    elevation, bbox, _lines = parse_contour_kml(_SAMPLE_KML, grid_size=20)

    assert elevation.shape == (20, 20)
    assert bbox.min_lon == pytest.approx(74.60)
    assert bbox.max_lat == pytest.approx(19.11)


def test_parse_contour_kml_accepts_a_kmz_archive():
    kmz_bytes = _as_kmz(_SAMPLE_KML)

    _elevation, _bbox, lines = parse_contour_kml(kmz_bytes)

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

"""HTTP-surface tests for POST /analyzeContour.

These deliberately stop at the upload boundary -- they assert on the form
field name and the file-type guard, not on analysis output, so they run
without a network round-trip to the rainfall and land-use APIs.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_accepts_the_upload_under_the_contour_map_field_name():
    # The graded submission requires the field be named exactly
    # "contour_map". FastAPI derives the form field name from the parameter
    # name, so this guards the endpoint signature against a rename.
    # Reaching the extension check proves the field itself was accepted.
    response = client.post(
        "/analyzeContour",
        files={"contour_map": ("survey.txt", b"not a survey", "text/plain")},
    )

    assert response.status_code == 422
    assert "expected a .kml or .kmz file" in response.text


def test_reports_contour_map_as_missing_when_sent_under_another_field_name():
    response = client.post(
        "/analyzeContour",
        files={"file": ("survey.kml", b"<kml/>", "application/vnd.google-earth.kml+xml")},
    )

    assert response.status_code == 422
    assert "contour_map" in response.text

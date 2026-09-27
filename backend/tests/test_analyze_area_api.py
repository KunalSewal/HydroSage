"""HTTP-surface tests for POST /analyzeArea.

The elevation fetch, catchment cache and rainfall/land lookups are
replaced with offline stand-ins, so these exercise the endpoint's own
logic (validation, siting inside the drawn area, response shape) without
spending OpenTopography quota or needing Redis.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point, Polygon

from app.api import analyze_area as analyze_area_module
from app.main import app
from app.schemas.recommend import RecommendationFieldsOut

client = TestClient(app)

# ~2.2 km square; the padded analysis extent reaches ~550 m beyond it on every side.
POLYGON = [[81.300, 21.200], [81.320, 21.200], [81.320, 21.220], [81.300, 21.220]]


class _FakeElevationClient:
    """Serves a synthetic DEM for whatever bbox is requested: a plane
    sloping down toward the north-west, so the unrestricted best pond site
    would sit outside the drawn area."""

    def get_dem_for_bbox(self, bbox, demtype="COP30", cache_key=None):
        size = 160
        y, x = np.mgrid[0:size, 0:size]
        return (x + y).astype(np.float64) + 200.0, bbox

    def close(self):
        pass


class _PassThroughCache:
    def get_or_compute(self, key, compute):
        return compute()


def _no_network_recommendation(lat, lon, bbox, catchment_area_m2, achievable):
    return RecommendationFieldsOut(
        average_annual_rainfall_mm=1200.0,
        runoff_volume_m3=catchment_area_m2 * 1.2 * 0.3,
        runoff_coefficient=0.3,
        pond_options=[],
        available_land_hectares=None,
    )


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(analyze_area_module, "ElevationClient", _FakeElevationClient)
    monkeypatch.setattr(
        analyze_area_module.CatchmentCache, "from_settings", classmethod(lambda cls, s: _PassThroughCache())
    )
    monkeypatch.setattr(analyze_area_module, "compute_recommendation_fields", _no_network_recommendation)


def test_sites_the_pond_inside_the_drawn_area(offline):
    response = client.post("/analyzeArea", json={"polygon": POLYGON})

    assert response.status_code == 200, response.text
    body = response.json()
    pond = Point(body["pond_location"]["lon"], body["pond_location"]["lat"])
    assert Polygon(POLYGON).buffer(1e-4).contains(pond)


def test_returns_pond_catchment_and_volume_for_the_map(offline):
    body = client.post("/analyzeArea", json={"polygon": POLYGON}).json()

    assert body["catchment_area_hectares"] > 0
    assert len(body["catchment_boundary"]) >= 4
    assert body["runoff_volume_m3"] > 0
    assert body["selected_area"] == POLYGON
    assert body["selected_area_hectares"] == pytest.approx(2.3 * 2.07 * 100, rel=0.05)
    assert body["contours"]


def test_rejects_an_area_too_small_before_fetching_elevation(offline):
    tiny = [[81.3, 21.2], [81.3003, 21.2], [81.3003, 21.2003], [81.3, 21.2003]]

    response = client.post("/analyzeArea", json={"polygon": tiny})

    assert response.status_code == 422
    assert "too small" in response.text


def test_rejects_an_area_too_large(offline):
    huge = [[81.0, 21.0], [81.5, 21.0], [81.5, 21.5], [81.0, 21.5]]

    response = client.post("/analyzeArea", json={"polygon": huge})

    assert response.status_code == 422
    assert "too large" in response.text


def test_rejects_fewer_than_three_points(offline):
    response = client.post("/analyzeArea", json={"polygon": [[81.3, 21.2], [81.31, 21.2]]})

    assert response.status_code == 422

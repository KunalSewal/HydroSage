import os

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.db import get_db
from app.infrastructure.village_repository import find_nearby
from app.main import app


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="needs live Postgres + Nominatim; set RUN_INTEGRATION_TESTS=1 to run",
)
def test_post_villages_creates_a_village_from_coordinates(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    assert find_nearby(db_session, lat=21.1938, lon=81.3509) is None  # proves the create path runs, not find_nearby

    response = client.post("/villages", json={"lat": 21.1938, "lon": 81.3509})

    assert response.status_code == 200
    body = response.json()
    assert body["lat"] == pytest.approx(21.1938, abs=0.001)
    assert body["lon"] == pytest.approx(81.3509, abs=0.001)
    assert body["state"]  # reverse-geocode filled something in
    app.dependency_overrides.clear()


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="needs live Postgres + Nominatim; set RUN_INTEGRATION_TESTS=1 to run",
)
def test_post_villages_reuses_a_nearby_existing_village(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    first = client.post("/villages", json={"lat": 21.1938, "lon": 81.3509})
    second = client.post("/villages", json={"lat": 21.19385, "lon": 81.35095})  # a few meters away

    assert first.json()["id"] == second.json()["id"]
    app.dependency_overrides.clear()


def test_post_villages_rejects_invalid_latitude():
    client = TestClient(app)
    response = client.post("/villages", json={"lat": 200.0, "lon": 74.6})
    assert response.status_code == 422

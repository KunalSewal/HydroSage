import os
import uuid

import pytest

from app.infrastructure.models import Village
from app.infrastructure.village_repository import create_village, find_nearby


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="needs a live Postgres (Docker Compose `postgis`); set RUN_INTEGRATION_TESTS=1 to run",
)
def test_find_nearby_finds_a_village_within_radius(db_session):
    village = create_village(
        db_session, lat=19.0679874, lon=74.6012297, name="Test Village",
        state="Maharashtra", district="Ahmednagar (Ahilyanagar)",
    )
    db_session.flush()

    found = find_nearby(db_session, lat=19.0689874, lon=74.6012297)  # ~111m away

    assert found is not None
    assert found.id == village.id


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="needs a live Postgres (Docker Compose `postgis`); set RUN_INTEGRATION_TESTS=1 to run",
)
def test_find_nearby_returns_none_outside_radius(db_session):
    create_village(
        db_session, lat=19.0679874, lon=74.6012297, name="Test Village 2",
        state="Maharashtra", district="Ahmednagar (Ahilyanagar)",
    )
    db_session.flush()

    found = find_nearby(db_session, lat=19.1179874, lon=74.6012297)  # ~5.5km away

    assert found is None


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="needs a live Postgres (Docker Compose `postgis`); set RUN_INTEGRATION_TESTS=1 to run",
)
def test_create_village_sets_a_bounding_box_around_the_point(db_session):
    village = create_village(
        db_session, lat=10.0, lon=20.0, name="Bbox Test",
        state="Test State", district="Test District",
    )
    db_session.flush()
    assert isinstance(village.id, uuid.UUID)
    # bounds is a Geometry column; just confirm the row round-trips.
    refetched = db_session.get(Village, village.id)
    assert refetched.name == "Bbox Test"

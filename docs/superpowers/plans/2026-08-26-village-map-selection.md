# Village Map Selection & Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Swagger-only backend demo with a real, premium-feeling map UI where a user picks any point (geolocated on open, searchable, or click-anywhere), and sees real contour geometry for that site rendered on the map — while swapping the elevation/geocoding providers off the now-unreliable OpenZenith per D-005.

**Architecture:** FastAPI backend gains a `geocoding_client.py` (Nominatim), a rewritten `elevation_client.py` (OpenTopography), and two endpoints (`GET /geocode`, `POST /villages`) on top of the already-working `GET /villages/{id}/elevation`. The frontend (currently the default Vite template) becomes a single-page map app: React + TypeScript + Tailwind CSS + Framer Motion + react-leaflet, with a `useSiteSelection` hook driving both the map (marker + contour rendering) and the side panel (staged status UI) from one source of truth.

**Tech Stack:** Backend: FastAPI, SQLAlchemy 2.0 + GeoAlchemy2, httpx, rasterio, pytest. Frontend: React 19 + TypeScript + Vite, Tailwind CSS v4, Framer Motion, react-leaflet, lucide-react, Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-08-26-village-map-selection-design.md` (amended for the OpenTopography/Nominatim switch — see `docs/DECISIONS.md` D-005 for why).

## Global Constraints

- Elevation: OpenTopography Global DEM API, `demtype=COP30`, GeoTIFF output. API key from `Settings.opentopography_api_key` (already in `backend/.env`, gitignored — never hardcode it).
- Geocoding: Nominatim public API directly. Every request MUST send `User-Agent: Settings.nominatim_user_agent` (usage-policy requirement) and the backend must not fire more than ~1 request/sec at it (single-user demo traffic makes this a non-issue, but don't add client-side retry loops that could violate it).
- `lat`/`lon` on any new endpoint: validated to real coordinate ranges (`-90..90`, `-180..180`) via Pydantic `Field` constraints.
- Contour coordinates from the backend are `[lon, lat]` pairs (GeoJSON order). Leaflet expects `[lat, lng]`. Every place the frontend consumes contour coordinates MUST flip this order — get it wrong and contours render in the wrong place with no error.
- No new backend dependency on Celery/Redis/MinIO for this plan — none of these tasks need the async job path; that's for the catchment-delineation work later.
- Every backend test that needs a live external API is marked `@pytest.mark.integration` and skipped unless `RUN_INTEGRATION_TESTS=1`, matching the existing convention in `tests/test_elevation_client.py`. Every backend test that needs the real Postgres gets the same treatment (Docker Compose's `postgis` service must be running).
- Deviation from the spec's literal component list, noted here so it isn't mistaken for a missed requirement: the spec describes `SitePanel.tsx` as "owning" the staged state machine, but `MapView` also needs that same state (to know when to show a marker and what contours to draw) — so the state machine is implemented as a standalone hook, `useSiteSelection` (Task 8), that `App` calls once and feeds to both `MapView` and `SitePanel` as props. `SitePanel` is still the component whose UI *is* that state machine's visible surface, and the spec's testing requirement ("component tests for SitePanel's state machine") is satisfied by testing the hook directly plus `SitePanel`'s rendering of every state it produces.

---

## Task 1: Rewrite `ElevationClient` for OpenTopography

**Files:**
- Modify: `backend/app/infrastructure/elevation_client.py` (full rewrite — the Terrarium tile-mosaic approach is replaced entirely)
- Modify: `backend/tests/test_elevation_client.py` (full rewrite)
- Modify: `backend/app/api/villages.py:1-53` (drop `DEM_ZOOM`, update the `get_dem_for_bbox` call)
- Modify: `backend/pyproject.toml` (rasterio is already a dependency; no change needed there, but confirm)

**Interfaces:**
- Produces: `BoundingBox(min_lon, min_lat, max_lon, max_lat)` (dataclass, same shape as before — `app/domain/terrain.py`'s `generate_contours` already consumes this, unchanged), `ElevationClient.get_dem_for_bbox(bbox: BoundingBox, demtype: str = "COP30") -> tuple[np.ndarray, BoundingBox]`, `ElevationClient.close() -> None`.

- [ ] **Step 1: Write the failing test**

Replace the full contents of `backend/tests/test_elevation_client.py`:

```python
import os

import numpy as np
import pytest

from app.infrastructure.elevation_client import BoundingBox, ElevationClient


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="hits the live OpenTopography API; set RUN_INTEGRATION_TESTS=1 to run",
)
def test_get_dem_for_bbox_returns_plausible_elevation_for_hiware_bazar():
    client = ElevationClient()
    # Hiware Bazar, Maharashtra — see docs/DECISIONS.md D-004. Known range
    # from a prior verified call: 662.8-959.2m for this exact bbox.
    bbox = BoundingBox(min_lon=74.53125, min_lat=19.020577, max_lon=74.663086, max_lat=19.103648)

    elevation, covered = client.get_dem_for_bbox(bbox)

    assert isinstance(elevation, np.ndarray)
    assert elevation.ndim == 2
    assert 600 < elevation.min() < 700
    assert 900 < elevation.max() < 1000
    assert covered.min_lon == pytest.approx(bbox.min_lon, abs=0.01)
    assert covered.max_lat == pytest.approx(bbox.max_lat, abs=0.01)
    client.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`, venv active): `RUN_INTEGRATION_TESTS=1 pytest tests/test_elevation_client.py -v`
Expected: FAIL — `ImportError` or `AttributeError`, since `ElevationClient.get_dem_for_bbox` still has the old `zoom` parameter and Terrarium-based internals that don't match this test's expectations (the old client has no `demtype` param and returns tile-snapped bounds, not OpenTopography-matching ones).

- [ ] **Step 3: Write minimal implementation**

Replace the full contents of `backend/app/infrastructure/elevation_client.py`:

```python
"""Client for OpenTopography's Global DEM API (Copernicus GLO-30, ~30m).

Replaced OpenZenith after it proved unreliable mid-project — see
docs/DECISIONS.md D-005 for the live verification data behind this switch.
"""

import io
from dataclasses import dataclass

import httpx
import numpy as np
import rasterio
from rasterio.io import MemoryFile

from app.core.config import get_settings


@dataclass(frozen=True)
class BoundingBox:
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float


class ElevationClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        settings = get_settings()
        self._api_key = settings.opentopography_api_key
        self._client = client or httpx.Client(
            base_url=settings.opentopography_base_url, timeout=30.0
        )

    def get_dem_for_bbox(
        self, bbox: BoundingBox, demtype: str = "COP30"
    ) -> tuple[np.ndarray, BoundingBox]:
        response = self._client.get(
            "/globaldem",
            params={
                "demtype": demtype,
                "south": bbox.min_lat,
                "north": bbox.max_lat,
                "west": bbox.min_lon,
                "east": bbox.max_lon,
                "outputFormat": "GTiff",
                "API_Key": self._api_key,
            },
        )
        response.raise_for_status()

        with MemoryFile(response.content) as memfile, memfile.open() as dataset:
            elevation = dataset.read(1).astype(np.float64)
            covered = BoundingBox(
                min_lon=dataset.bounds.left,
                min_lat=dataset.bounds.bottom,
                max_lon=dataset.bounds.right,
                max_lat=dataset.bounds.top,
            )

        return elevation, covered

    def close(self) -> None:
        self._client.close()
```

Now update the call site — edit `backend/app/api/villages.py`, remove the `DEM_ZOOM = 13` module-level constant and change:

```python
    client = ElevationClient()
    try:
        mosaic, covered = client.get_dem_for_bbox(bbox, zoom=DEM_ZOOM)
    finally:
        client.close()
```

to:

```python
    client = ElevationClient()
    try:
        mosaic, covered = client.get_dem_for_bbox(bbox)
    finally:
        client.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `RUN_INTEGRATION_TESTS=1 pytest tests/test_elevation_client.py -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite to check nothing else broke**

Run: `pytest -q` (without `RUN_INTEGRATION_TESTS` — the integration test should show as skipped, everything else should pass, including `tests/test_terrain.py` and `tests/test_health.py`)
Expected: all non-integration tests PASS, 1 skipped

- [ ] **Step 6: Manually verify against the running stack**

With `docker compose up -d --build api` (from the repo root) and `docker compose exec api python scripts/seed_villages.py` already run once (or already seeded from before):
```
curl http://localhost:8000/villages/68651d2d-a9c1-453b-abba-9c92b2ab8181/elevation
```
Expected: real JSON with `min_elevation` around 662 and `max_elevation` around 959 (same village as before, new provider).

- [ ] **Step 7: Commit**

```bash
git add backend/app/infrastructure/elevation_client.py backend/tests/test_elevation_client.py backend/app/api/villages.py
git commit -m "Switch ElevationClient from OpenZenith to OpenTopography (D-005)"
```

---

## Task 2: `GeocodingClient` (Nominatim) and `GET /geocode`

**Files:**
- Create: `backend/app/infrastructure/geocoding_client.py`
- Create: `backend/tests/test_geocoding_client.py`
- Create: `backend/app/api/geocode.py`
- Create: `backend/app/schemas/geocode.py`
- Modify: `backend/app/main.py:1-27` (register the new router)

**Interfaces:**
- Produces: `GeocodingClient.search(query: str, limit: int = 5) -> list[dict]` (each dict has at least `display_name`, `lat`, `lon` as returned by Nominatim — lat/lon come back as **strings**, callers must `float()` them), `GeocodingClient.reverse(lat: float, lon: float) -> dict | None` (`None` when Nominatim returns `{"error": ...}`, i.e. unresolvable point), `GeocodingClient.close() -> None`.
- Produces (schema): `GeocodeResultOut(display_name: str, lat: float, lon: float)`.
- Consumes: `Settings.nominatim_base_url`, `Settings.nominatim_user_agent` (`backend/app/core/config.py`, already added).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_geocoding_client.py`:

```python
import os

import pytest

from app.infrastructure.geocoding_client import GeocodingClient


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="hits the live Nominatim API; set RUN_INTEGRATION_TESTS=1 to run",
)
def test_search_finds_hiware_bazar():
    client = GeocodingClient()
    results = client.search("Hiware Bazar, Maharashtra, India", limit=1)
    assert len(results) == 1
    assert "Hiware" in results[0]["display_name"]
    assert float(results[0]["lat"]) == pytest.approx(19.0679874, abs=0.01)
    client.close()


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="hits the live Nominatim API; set RUN_INTEGRATION_TESTS=1 to run",
)
def test_reverse_resolves_a_known_point():
    client = GeocodingClient()
    result = client.reverse(21.1938, 81.3509)  # Bhilai/Durg default map center
    assert result is not None
    assert "Chhattisgarh" in result["display_name"]
    client.close()


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="hits the live Nominatim API; set RUN_INTEGRATION_TESTS=1 to run",
)
def test_reverse_returns_none_for_unresolvable_point():
    client = GeocodingClient()
    result = client.reverse(0, 0)  # open ocean
    assert result is None
    client.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `RUN_INTEGRATION_TESTS=1 pytest tests/test_geocoding_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.infrastructure.geocoding_client'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/infrastructure/geocoding_client.py`:

```python
"""Client for Nominatim (OpenStreetMap) geocoding. See docs/DECISIONS.md D-005."""

import httpx

from app.core.config import get_settings


class GeocodingClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        settings = get_settings()
        self._client = client or httpx.Client(
            base_url=settings.nominatim_base_url,
            timeout=15.0,
            headers={"User-Agent": settings.nominatim_user_agent},
        )

    def search(self, query: str, limit: int = 5) -> list[dict]:
        response = self._client.get(
            "/search", params={"q": query, "format": "jsonv2", "limit": limit}
        )
        response.raise_for_status()
        return response.json()

    def reverse(self, lat: float, lon: float) -> dict | None:
        response = self._client.get(
            "/reverse", params={"lat": lat, "lon": lon, "format": "jsonv2"}
        )
        response.raise_for_status()
        data = response.json()
        return None if "error" in data else data

    def close(self) -> None:
        self._client.close()
```

Create `backend/app/schemas/geocode.py`:

```python
from pydantic import BaseModel


class GeocodeResultOut(BaseModel):
    display_name: str
    lat: float
    lon: float
```

Create `backend/app/api/geocode.py`:

```python
from fastapi import APIRouter, Query

from app.infrastructure.geocoding_client import GeocodingClient
from app.schemas.geocode import GeocodeResultOut

router = APIRouter(tags=["geocode"])


@router.get("/geocode", response_model=list[GeocodeResultOut])
def search_places(query: str = Query(..., min_length=1)):
    client = GeocodingClient()
    try:
        results = client.search(query)
    finally:
        client.close()
    return [
        GeocodeResultOut(display_name=r["display_name"], lat=float(r["lat"]), lon=float(r["lon"]))
        for r in results
    ]
```

Modify `backend/app/main.py` — add the import and router registration:

```python
from app.api import catchment, geocode, jobs, rainfall, recommend, report, satellite, villages
```

```python
app.include_router(geocode.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `RUN_INTEGRATION_TESTS=1 pytest tests/test_geocoding_client.py -v`
Expected: PASS

- [ ] **Step 5: Manually verify the endpoint**

With the API running (`docker compose up -d --build api` or `uvicorn app.main:app --reload` locally):
```
curl "http://localhost:8000/geocode?query=Hiware+Bazar"
```
Expected: JSON array with one result containing `"display_name"` mentioning Hiware Bazar.

- [ ] **Step 6: Commit**

```bash
git add backend/app/infrastructure/geocoding_client.py backend/tests/test_geocoding_client.py backend/app/api/geocode.py backend/app/schemas/geocode.py backend/app/main.py
git commit -m "Add GeocodingClient (Nominatim) and GET /geocode"
```

---

## Task 3: Village find-or-create repository

**Files:**
- Create: `backend/app/infrastructure/village_repository.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_village_repository.py`
- Modify: `backend/scripts/seed_villages.py:1-24` (reuse the shared default extent constant)

**Interfaces:**
- Produces: `DEFAULT_HALF_EXTENT_DEG: float = 0.03` (module-level constant), `find_nearby(db: Session, lat: float, lon: float, radius_m: float = 500.0) -> Village | None`, `create_village(db: Session, lat: float, lon: float, name: str, state: str, district: str) -> Village`.
- Consumes: `app.infrastructure.models.Village`, `app.infrastructure.db.SessionLocal`.

- [ ] **Step 1: Write the DB test fixture**

Create `backend/tests/conftest.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings


@pytest.fixture()
def db_session():
    """A real Postgres session (via the Docker Compose `postgis` service)
    wrapped in a transaction that's rolled back after the test, so tests
    don't leave data behind or depend on ordering."""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    connection = engine.connect()
    transaction = connection.begin()
    TestSession = sessionmaker(bind=connection)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_village_repository.py`:

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run (Docker Compose `postgis` must be up — `docker compose up -d postgis`): `RUN_INTEGRATION_TESTS=1 pytest tests/test_village_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.infrastructure.village_repository'`

- [ ] **Step 4: Write minimal implementation**

Create `backend/app/infrastructure/village_repository.py`:

```python
import uuid

from geoalchemy2 import Geography
from geoalchemy2.elements import WKTElement
from geoalchemy2.functions import ST_DWithin
from geoalchemy2.shape import from_shape
from shapely.geometry import Point, box
from sqlalchemy import cast
from sqlalchemy.orm import Session

from app.infrastructure.models import Village

DEFAULT_HALF_EXTENT_DEG = 0.03  # ~3km — village + surrounding catchment, see D-004
FIND_NEARBY_RADIUS_M = 500.0


def find_nearby(db: Session, lat: float, lon: float, radius_m: float = FIND_NEARBY_RADIUS_M) -> Village | None:
    point = WKTElement(f"POINT({lon} {lat})", srid=4326)
    return (
        db.query(Village)
        .filter(ST_DWithin(cast(Village.centroid, Geography), cast(point, Geography), radius_m))
        .first()
    )


def create_village(
    db: Session, lat: float, lon: float, name: str, state: str, district: str
) -> Village:
    centroid = Point(lon, lat)
    e = DEFAULT_HALF_EXTENT_DEG
    bounds = box(lon - e, lat - e, lon + e, lat + e)

    village = Village(
        id=uuid.uuid4(),
        name=name,
        state=state,
        district=district,
        centroid=from_shape(centroid, srid=4326),
        bounds=from_shape(bounds, srid=4326),
    )
    db.add(village)
    return village
```

Modify `backend/scripts/seed_villages.py` — replace the hardcoded `"half_extent_deg": 0.03` field and its use with the shared constant, so seeding and dynamic creation can't drift apart:

```python
from app.infrastructure.db import SessionLocal
from app.infrastructure.models import Village
from app.infrastructure.village_repository import DEFAULT_HALF_EXTENT_DEG

VILLAGES = [
    {
        "name": "Hiware Bazar",
        "state": "Maharashtra",
        "district": "Ahmednagar (Ahilyanagar)",
        "lat": 19.0679874,
        "lon": 74.6012297,
    },
]
```

and in the loop, replace `e = v["half_extent_deg"]` with `e = DEFAULT_HALF_EXTENT_DEG`.

- [ ] **Step 5: Run test to verify it passes**

Run: `RUN_INTEGRATION_TESTS=1 pytest tests/test_village_repository.py -v`
Expected: PASS (all three tests)

- [ ] **Step 6: Verify the seed script still works**

Run: `python scripts/seed_villages.py`
Expected: `skip Hiware Bazar — already seeded (<uuid>)` (or `seeded Hiware Bazar (<uuid>)` on a fresh DB) — no errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/infrastructure/village_repository.py backend/tests/conftest.py backend/tests/test_village_repository.py backend/scripts/seed_villages.py
git commit -m "Add village find-or-create repository with proximity dedup"
```

---

## Task 4: `POST /villages`

**Files:**
- Modify: `backend/app/schemas/village.py:1-32` (add `VillageCreate`)
- Modify: `backend/app/api/villages.py` (add the endpoint)
- Create: `backend/tests/test_villages_api.py`

**Interfaces:**
- Consumes: `find_nearby`, `create_village` (Task 3), `GeocodingClient.reverse` (Task 2), `VillageOut` (existing).
- Produces: `VillageCreate(lat: float, lon: float)` request schema; `POST /villages` → `VillageOut`, 422 on invalid coordinates or an unresolvable point.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_villages_api.py`:

```python
import os

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.db import get_db
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

    response = client.post("/villages", json={"lat": 19.0679874, "lon": 74.6012297})

    assert response.status_code == 200
    body = response.json()
    assert body["lat"] == pytest.approx(19.0679874, abs=0.001)
    assert body["lon"] == pytest.approx(74.6012297, abs=0.001)
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

    first = client.post("/villages", json={"lat": 19.0679874, "lon": 74.6012297})
    second = client.post("/villages", json={"lat": 19.0680000, "lon": 74.6012500})  # a few meters away

    assert first.json()["id"] == second.json()["id"]
    app.dependency_overrides.clear()


def test_post_villages_rejects_invalid_latitude():
    client = TestClient(app)
    response = client.post("/villages", json={"lat": 200.0, "lon": 74.6})
    assert response.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `RUN_INTEGRATION_TESTS=1 pytest tests/test_villages_api.py -v`
Expected: the first two tests FAIL with 404 (no `POST /villages` route yet); the third (no integration marker) FAILs too, since with no route at all FastAPI returns 404, not 422.

- [ ] **Step 3: Write minimal implementation**

Modify `backend/app/schemas/village.py` — add after the `VillageOut` class:

```python
from pydantic import BaseModel, Field


class VillageCreate(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
```

(note: `pydantic` is already imported for `BaseModel` at the top of the file — just add `Field` to that existing import line instead of a second import line.)

Modify `backend/app/api/villages.py` — add these imports:

```python
from app.infrastructure.geocoding_client import GeocodingClient
from app.infrastructure.village_repository import create_village, find_nearby
from app.schemas.village import BoundingBoxOut, ElevationOut, VillageCreate, VillageOut
```

and add the new endpoint (after `list_villages`, before `get_elevation`):

```python
@router.post("", response_model=VillageOut)
def create_village_from_point(payload: VillageCreate, db: Session = Depends(get_db)):
    existing = find_nearby(db, lat=payload.lat, lon=payload.lon)
    if existing is not None:
        return VillageOut(
            id=existing.id,
            name=existing.name,
            state=existing.state,
            district=existing.district,
            lat=payload.lat,
            lon=payload.lon,
        )

    geocoder = GeocodingClient()
    try:
        place = geocoder.reverse(payload.lat, payload.lon)
    finally:
        geocoder.close()

    if place is None:
        raise HTTPException(status_code=422, detail="couldn't identify a site at this location")

    address = place.get("address", {})
    name = place.get("name") or address.get("city") or address.get("town") or address.get("village") or place["display_name"].split(",")[0]
    state = address.get("state", "")
    district = address.get("state_district") or address.get("county") or ""

    village = create_village(db, lat=payload.lat, lon=payload.lon, name=name, state=state, district=district)
    db.commit()

    return VillageOut(id=village.id, name=name, state=state, district=district, lat=payload.lat, lon=payload.lon)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `RUN_INTEGRATION_TESTS=1 pytest tests/test_villages_api.py -v`
Expected: all three PASS

- [ ] **Step 5: Run the full backend suite**

Run: `pytest -q` (no `RUN_INTEGRATION_TESTS`)
Expected: all non-integration tests pass; integration tests show as skipped.

Then: `RUN_INTEGRATION_TESTS=1 pytest -q` (Docker Compose `postgis` up)
Expected: everything passes.

- [ ] **Step 6: Manually verify against the running stack**

```
docker compose up -d --build api
curl -X POST http://localhost:8000/villages -H "Content-Type: application/json" -d "{\"lat\": 21.1938, \"lon\": 81.3509}"
```
Expected: JSON with a real `id`, and `district`/`state` mentioning Durg/Chhattisgarh.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/village.py backend/app/api/villages.py backend/tests/test_villages_api.py
git commit -m "Add POST /villages: find-or-create from a lat/lon click"
```

---

## Task 5: Frontend tooling — Tailwind, Framer Motion, lucide-react, Vitest, base shell

**Files:**
- Modify: `frontend/package.json` (new deps)
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/src/index.css` (full replace)
- Modify: `frontend/index.html` (font links, title)
- Modify: `frontend/src/App.tsx` (full replace — strip Vite boilerplate)
- Delete: `frontend/src/App.css`, `frontend/src/assets/react.svg`, `frontend/src/assets/vite.svg`, `frontend/src/assets/hero.png`
- Create: `frontend/src/test-setup.ts`

**Interfaces:**
- Produces: a working `npm run dev` / `npm run build` with Tailwind utility classes available, Framer Motion and lucide-react importable, and `npm run test` running Vitest.

- [ ] **Step 1: Install the new dependencies**

From `frontend/`:
```bash
npm install tailwindcss @tailwindcss/vite framer-motion lucide-react
npm install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```

- [ ] **Step 2: Configure Tailwind in Vite**

Edit `frontend/vite.config.ts`:

```ts
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test-setup.ts',
  },
})
```

- [ ] **Step 3: Add the Vitest setup file**

Create `frontend/src/test-setup.ts`:

```ts
import '@testing-library/jest-dom/vitest'
```

- [ ] **Step 4: Add the `test` script**

Edit `frontend/package.json` — add to `"scripts"`:

```json
    "test": "vitest run"
```

- [ ] **Step 5: Replace the stylesheet with Tailwind + design tokens**

Replace the full contents of `frontend/src/index.css`:

```css
@import "tailwindcss";

@theme {
  --font-display: "Space Grotesk", "Inter", system-ui, sans-serif;
  --font-sans: "Inter", system-ui, sans-serif;
}

html, body, #root {
  height: 100%;
  margin: 0;
}

body {
  font-family: var(--font-sans);
  background-color: #0b1220;
  color: #e7ecf5;
}

@keyframes marker-bounce-in {
  0% { transform: scale(0) translateY(-20px); opacity: 0; }
  60% { transform: scale(1.2) translateY(0); opacity: 1; }
  100% { transform: scale(1) translateY(0); }
}
.marker-bounce {
  animation: marker-bounce-in 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
}
```

- [ ] **Step 6: Load the font pairing**

Edit `frontend/index.html` — add inside `<head>`, before the existing `<title>` line, and update the title:

```html
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet" />
    <title>HydroSage</title>
```

(remove the old `<title>frontend</title>` line it's replacing.)

- [ ] **Step 7: Strip the Vite boilerplate**

Delete `frontend/src/App.css`, `frontend/src/assets/react.svg`, `frontend/src/assets/vite.svg`, `frontend/src/assets/hero.png`.

Replace the full contents of `frontend/src/App.tsx` with a minimal shell (later tasks fill this in):

```tsx
function App() {
  return (
    <div className="flex h-full w-full items-center justify-center">
      <p className="font-display text-lg text-slate-300">HydroSage</p>
    </div>
  )
}

export default App
```

- [ ] **Step 8: Verify the build and test runner both work**

Run: `npm run build`
Expected: succeeds, no Tailwind/PostCSS errors.

Run: `npm run test`
Expected: "No test files found" (expected — none written yet) but exits without a config error.

- [ ] **Step 9: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/src/index.css frontend/index.html frontend/src/App.tsx frontend/src/test-setup.ts
git rm frontend/src/App.css frontend/src/assets/react.svg frontend/src/assets/vite.svg frontend/src/assets/hero.png
git commit -m "Frontend tooling: Tailwind, Framer Motion, lucide-react, Vitest"
```

---

## Task 6: Typed API client

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/client.test.ts`

**Interfaces:**
- Produces: `Village`, `Contour`, `BoundingBox`, `ElevationData`, `GeocodeResult` types; `listVillages()`, `createVillage(lat, lon)`, `getElevation(villageId)`, `searchPlaces(query)` functions, each returning a `Promise` of the matching type and throwing an `Error` with a readable message on a non-OK response.
- Consumes: nothing from earlier tasks (this is the base layer everything else builds on).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/api/client.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createVillage, getElevation, listVillages, searchPlaces } from './client'

describe('api client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('listVillages returns parsed JSON on success', async () => {
    const villages = [{ id: '1', name: 'Test', state: 'MH', district: 'Test Dist', lat: 1, lon: 2 }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(villages) }))

    const result = await listVillages()

    expect(result).toEqual(villages)
  })

  it('createVillage posts lat/lon and returns the created village', async () => {
    const village = { id: '2', name: 'New', state: 'CG', district: 'Durg', lat: 21.19, lon: 81.35 }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(village) })
    vi.stubGlobal('fetch', fetchMock)

    const result = await createVillage(21.19, 81.35)

    expect(result).toEqual(village)
    const [, options] = fetchMock.mock.calls[0]
    expect(JSON.parse(options.body)).toEqual({ lat: 21.19, lon: 81.35 })
  })

  it('getElevation throws a readable error on a non-OK response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404, json: () => Promise.resolve({ detail: 'village not found' }) }))

    await expect(getElevation('missing-id')).rejects.toThrow('village not found')
  })

  it('searchPlaces returns parsed results', async () => {
    const results = [{ display_name: 'Bhilai, Chhattisgarh', lat: 21.19, lon: 81.35 }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(results) }))

    const result = await searchPlaces('Bhilai')

    expect(result).toEqual(results)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `frontend/`): `npm run test`
Expected: FAIL — `Failed to resolve import "./client"`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/api/client.ts`:

```ts
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export interface Village {
  id: string
  name: string
  state: string
  district: string
  lat: number
  lon: number
}

export interface Contour {
  elevation: number
  coordinates: [number, number][] // [lon, lat] — GeoJSON order, NOT Leaflet order
}

export interface BoundingBox {
  min_lon: number
  min_lat: number
  max_lon: number
  max_lat: number
}

export interface ElevationData {
  village_id: string
  bbox: BoundingBox
  min_elevation: number
  max_elevation: number
  contours: Contour[]
}

export interface GeocodeResult {
  display_name: string
  lat: number
  lon: number
}

async function parseOrThrow<T>(response: Response): Promise<T> {
  const body = await response.json()
  if (!response.ok) {
    throw new Error(body.detail ?? `request failed with status ${response.status}`)
  }
  return body as T
}

export async function listVillages(): Promise<Village[]> {
  const response = await fetch(`${API_BASE}/villages`)
  return parseOrThrow<Village[]>(response)
}

export async function createVillage(lat: number, lon: number): Promise<Village> {
  const response = await fetch(`${API_BASE}/villages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lat, lon }),
  })
  return parseOrThrow<Village>(response)
}

export async function getElevation(villageId: string): Promise<ElevationData> {
  const response = await fetch(`${API_BASE}/villages/${villageId}/elevation`)
  return parseOrThrow<ElevationData>(response)
}

export async function searchPlaces(query: string): Promise<GeocodeResult[]> {
  const response = await fetch(`${API_BASE}/geocode?query=${encodeURIComponent(query)}`)
  return parseOrThrow<GeocodeResult[]>(response)
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/api/client.test.ts
git commit -m "Add typed API client for villages/elevation/geocode"
```

---

## Task 7: `useGeolocation` hook

**Files:**
- Create: `frontend/src/hooks/useGeolocation.ts`
- Create: `frontend/src/hooks/useGeolocation.test.ts`

**Interfaces:**
- Produces: `DEFAULT_CENTER: { lat: number; lon: number }` (Bhilai/Durg, 21.19, 81.30), `useGeolocation()` returning `{ position: { lat: number; lon: number }, status: 'locating' | 'located' | 'unavailable', locate: () => void }`. `position` is always populated (the default center while `status === 'locating'` or on `'unavailable'`, the real position once `'located'`) so consumers never need a null check.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/hooks/useGeolocation.test.ts`:

```ts
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DEFAULT_CENTER, useGeolocation } from './useGeolocation'

describe('useGeolocation', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('starts locating and resolves to the real position on success', async () => {
    const getCurrentPosition = vi.fn((success: PositionCallback) => {
      success({ coords: { latitude: 19.0, longitude: 74.0 } } as GeolocationPosition)
    })
    vi.stubGlobal('navigator', { geolocation: { getCurrentPosition } })

    const { result } = renderHook(() => useGeolocation())

    expect(result.current.status).toBe('locating')
    await waitFor(() => expect(result.current.status).toBe('located'))
    expect(result.current.position).toEqual({ lat: 19.0, lon: 74.0 })
  })

  it('falls back to the default center when permission is denied', async () => {
    const getCurrentPosition = vi.fn((_success: PositionCallback, error: PositionErrorCallback) => {
      error({ code: 1, message: 'denied' } as GeolocationPositionError)
    })
    vi.stubGlobal('navigator', { geolocation: { getCurrentPosition } })

    const { result } = renderHook(() => useGeolocation())

    await waitFor(() => expect(result.current.status).toBe('unavailable'))
    expect(result.current.position).toEqual(DEFAULT_CENTER)
  })

  it('falls back to the default center when geolocation is not supported', async () => {
    vi.stubGlobal('navigator', {})

    const { result } = renderHook(() => useGeolocation())

    await waitFor(() => expect(result.current.status).toBe('unavailable'))
    expect(result.current.position).toEqual(DEFAULT_CENTER)
  })

  it('locate() re-triggers the lookup', async () => {
    const getCurrentPosition = vi.fn((success: PositionCallback) => {
      success({ coords: { latitude: 19.0, longitude: 74.0 } } as GeolocationPosition)
    })
    vi.stubGlobal('navigator', { geolocation: { getCurrentPosition } })

    const { result } = renderHook(() => useGeolocation())
    await waitFor(() => expect(result.current.status).toBe('located'))

    act(() => result.current.locate())

    expect(getCurrentPosition).toHaveBeenCalledTimes(2)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test`
Expected: FAIL — `Failed to resolve import "./useGeolocation"`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/hooks/useGeolocation.ts`:

```ts
import { useCallback, useEffect, useState } from 'react'

export const DEFAULT_CENTER = { lat: 21.19, lon: 81.3 } // Bhilai/Durg, Chhattisgarh

export type GeolocationStatus = 'locating' | 'located' | 'unavailable'

export interface GeolocationResult {
  position: { lat: number; lon: number }
  status: GeolocationStatus
  locate: () => void
}

export function useGeolocation(): GeolocationResult {
  const [position, setPosition] = useState(DEFAULT_CENTER)
  const [status, setStatus] = useState<GeolocationStatus>('locating')

  const locate = useCallback(() => {
    if (!('geolocation' in navigator)) {
      setStatus('unavailable')
      return
    }
    setStatus('locating')
    navigator.geolocation.getCurrentPosition(
      (result) => {
        setPosition({ lat: result.coords.latitude, lon: result.coords.longitude })
        setStatus('located')
      },
      () => {
        setPosition(DEFAULT_CENTER)
        setStatus('unavailable')
      },
    )
  }, [])

  useEffect(() => {
    locate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { position, status, locate }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useGeolocation.ts frontend/src/hooks/useGeolocation.test.ts
git commit -m "Add useGeolocation hook with Bhilai/Durg default fallback"
```

---

## Task 8: `useSiteSelection` hook (the staged state machine)

**Files:**
- Create: `frontend/src/hooks/useSiteSelection.ts`
- Create: `frontend/src/hooks/useSiteSelection.test.ts`

**Interfaces:**
- Consumes: `createVillage`, `getElevation` (Task 6).
- Produces: `SiteStatus = 'idle' | 'locating' | 'located' | 'analyzing' | 'analyzed' | 'error'`, `useSiteSelection()` returning `{ state: { status, village: Village | null, elevation: ElevationData | null, errorMessage: string | null, lastPoint: { lat: number; lon: number } | null }, selectPoint: (lat, lon) => Promise<void>, analyze: () => Promise<void> }`. `lastPoint` is set to whatever was passed to `selectPoint` even on failure, specifically so a caller can retry the point that actually failed rather than something unrelated (e.g. the browser's current geolocation) — see Task 11.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/hooks/useSiteSelection.test.ts`:

```ts
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as client from '../api/client'
import { useSiteSelection } from './useSiteSelection'

vi.mock('../api/client')

const village = { id: 'v1', name: 'Test Village', state: 'CG', district: 'Durg', lat: 21.19, lon: 81.3 }
const elevation = {
  village_id: 'v1',
  bbox: { min_lon: 81.2, min_lat: 21.1, max_lon: 81.4, max_lat: 21.3 },
  min_elevation: 250,
  max_elevation: 300,
  contours: [],
}

describe('useSiteSelection', () => {
  beforeEach(() => {
    vi.mocked(client.createVillage).mockResolvedValue(village)
    vi.mocked(client.getElevation).mockResolvedValue(elevation)
  })

  it('starts idle', () => {
    const { result } = renderHook(() => useSiteSelection())
    expect(result.current.state.status).toBe('idle')
  })

  it('selectPoint moves idle -> locating -> located with the village set', async () => {
    const { result } = renderHook(() => useSiteSelection())

    act(() => {
      result.current.selectPoint(21.19, 81.3)
    })
    expect(result.current.state.status).toBe('locating')

    await waitFor(() => expect(result.current.state.status).toBe('located'))
    expect(result.current.state.village).toEqual(village)
  })

  it('analyze moves located -> analyzing -> analyzed with elevation set', async () => {
    const { result } = renderHook(() => useSiteSelection())
    await act(() => result.current.selectPoint(21.19, 81.3))
    await waitFor(() => expect(result.current.state.status).toBe('located'))

    act(() => {
      result.current.analyze()
    })
    expect(result.current.state.status).toBe('analyzing')

    await waitFor(() => expect(result.current.state.status).toBe('analyzed'))
    expect(result.current.state.elevation).toEqual(elevation)
  })

  it('selectPoint failure moves to error with a message, but keeps the attempted point', async () => {
    vi.mocked(client.createVillage).mockRejectedValue(new Error("couldn't identify a site here"))
    const { result } = renderHook(() => useSiteSelection())

    await act(() => result.current.selectPoint(0, 0))

    expect(result.current.state.status).toBe('error')
    expect(result.current.state.errorMessage).toBe("couldn't identify a site here")
    expect(result.current.state.lastPoint).toEqual({ lat: 0, lon: 0 })
  })

  it('analyze failure moves to error with a message', async () => {
    vi.mocked(client.getElevation).mockRejectedValue(new Error('elevation service unavailable'))
    const { result } = renderHook(() => useSiteSelection())
    await act(() => result.current.selectPoint(21.19, 81.3))
    await waitFor(() => expect(result.current.state.status).toBe('located'))

    await act(() => result.current.analyze())

    expect(result.current.state.status).toBe('error')
    expect(result.current.state.errorMessage).toBe('elevation service unavailable')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test`
Expected: FAIL — `Failed to resolve import "./useSiteSelection"`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/hooks/useSiteSelection.ts`:

```ts
import { useCallback, useState } from 'react'
import { createVillage, getElevation, type ElevationData, type Village } from '../api/client'

export type SiteStatus = 'idle' | 'locating' | 'located' | 'analyzing' | 'analyzed' | 'error'

export interface SiteSelectionState {
  status: SiteStatus
  village: Village | null
  elevation: ElevationData | null
  errorMessage: string | null
  lastPoint: { lat: number; lon: number } | null
}

const initialState: SiteSelectionState = {
  status: 'idle',
  village: null,
  elevation: null,
  errorMessage: null,
  lastPoint: null,
}

export function useSiteSelection() {
  const [state, setState] = useState<SiteSelectionState>(initialState)

  const selectPoint = useCallback(async (lat: number, lon: number) => {
    setState((prev) => ({ ...prev, status: 'locating', errorMessage: null, lastPoint: { lat, lon } }))
    try {
      const village = await createVillage(lat, lon)
      setState((prev) => ({ ...prev, status: 'located', village, elevation: null }))
    } catch (error) {
      setState((prev) => ({
        ...prev,
        status: 'error',
        errorMessage: error instanceof Error ? error.message : 'something went wrong',
      }))
    }
  }, [])

  const analyze = useCallback(async () => {
    setState((prev) => {
      if (!prev.village) return prev
      return { ...prev, status: 'analyzing', errorMessage: null }
    })
    setState((current) => {
      if (current.status !== 'analyzing' || !current.village) return current
      getElevation(current.village.id)
        .then((elevation) => {
          setState((prev) => ({ ...prev, status: 'analyzed', elevation }))
        })
        .catch((error: unknown) => {
          setState((prev) => ({
            ...prev,
            status: 'error',
            errorMessage: error instanceof Error ? error.message : 'something went wrong',
          }))
        })
      return current
    })
  }, [])

  return { state, selectPoint, analyze }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test`
Expected: PASS (5 tests). If `analyze`'s nested-`setState` pattern above causes a stale-closure issue (double-check the `current.village` read happens against fresh state), simplify to reading `state.village` directly via a `useCallback` dependency array of `[state.village]` instead — either is acceptable as long as the test passes; prefer whichever reads more clearly once it's green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useSiteSelection.ts frontend/src/hooks/useSiteSelection.test.ts
git commit -m "Add useSiteSelection hook: idle/locating/located/analyzing/analyzed/error"
```

---

## Task 9: `MapView` component

**Files:**
- Create: `frontend/src/components/MapView.tsx`

**Interfaces:**
- Consumes: `Contour` (Task 6), `useSiteSelection`'s `state.village`/`state.elevation`/`state.status` shape (Task 8) — passed in as props, not called directly (keeps `MapView` presentational and independent of the hook's internals).
- Produces: `MapViewProps { center: { lat: number; lon: number }; markerPosition: { lat: number; lon: number } | null; contours: Contour[]; onMapClick: (lat: number, lon: number) => void }`, default export `MapView`.

No test for this task — it's a thin wrapper over `react-leaflet` (a well-tested third-party library) whose behavior is the map rendering itself, which isn't meaningfully unit-testable in jsdom (Leaflet needs real layout/canvas). It's verified manually in Task 11 once wired into `App`.

- [ ] **Step 1: Write the component**

Create `frontend/src/components/MapView.tsx`:

```tsx
import L from 'leaflet'
import { useEffect, useState } from 'react'
import { MapContainer, Marker, Polyline, TileLayer, useMapEvents } from 'react-leaflet'
import type { Contour } from '../api/client'

// A fresh element per distinct position (see the `key` on <Marker> below)
// is required for the CSS mount animation to replay on every new click —
// react-leaflet otherwise reuses the same DOM node and just moves it.
const markerIcon = L.divIcon({
  className: 'hydrosage-marker',
  html: '<div class="marker-bounce h-4 w-4 rounded-full bg-sky-400 ring-4 ring-sky-400/30"></div>',
  iconSize: [16, 16],
  iconAnchor: [8, 8],
})

interface MapViewProps {
  center: { lat: number; lon: number }
  markerPosition: { lat: number; lon: number } | null
  contours: Contour[]
  onMapClick: (lat: number, lon: number) => void
}

function ClickHandler({ onMapClick }: { onMapClick: (lat: number, lon: number) => void }) {
  useMapEvents({
    click(event) {
      onMapClick(event.latlng.lat, event.latlng.lng)
    },
  })
  return null
}

// Contours arrive as [lon, lat] (GeoJSON order); Leaflet wants [lat, lng].
// Revealed a few at a time on a short interval for a "drawing in" feel
// rather than every line snapping in at once.
function ContourLayer({ contours }: { contours: Contour[] }) {
  const [visibleCount, setVisibleCount] = useState(0)

  useEffect(() => {
    setVisibleCount(0)
    if (contours.length === 0) return
    const step = Math.max(1, Math.ceil(contours.length / 20))
    const interval = setInterval(() => {
      setVisibleCount((count) => {
        const next = count + step
        if (next >= contours.length) clearInterval(interval)
        return Math.min(next, contours.length)
      })
    }, 40)
    return () => clearInterval(interval)
  }, [contours])

  return (
    <>
      {contours.slice(0, visibleCount).map((contour, index) => (
        <Polyline
          key={index}
          positions={contour.coordinates.map(([lon, lat]) => [lat, lon])}
          pathOptions={{ color: '#38bdf8', weight: 1.5, opacity: 0.8 }}
        />
      ))}
    </>
  )
}

export default function MapView({ center, markerPosition, contours, onMapClick }: MapViewProps) {
  return (
    <MapContainer center={[center.lat, center.lon]} zoom={12} className="h-full w-full">
      <TileLayer
        attribution="Tiles &copy; Esri"
        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
      />
      <ClickHandler onMapClick={onMapClick} />
      {markerPosition && (
        <Marker
          key={`${markerPosition.lat}-${markerPosition.lon}`}
          position={[markerPosition.lat, markerPosition.lon]}
          icon={markerIcon}
        />
      )}
      <ContourLayer contours={contours} />
    </MapContainer>
  )
}
```

- [ ] **Step 2: Verify it compiles**

Run (from `frontend/`): `npm run build`
Expected: succeeds with no TypeScript errors. (Full behavioral verification happens in Task 11 once `App.tsx` renders it for real.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/MapView.tsx
git commit -m "Add MapView: click-to-select map with Esri imagery and staged contour reveal"
```

---

## Task 10: `SearchBox` and `SitePanel` components

**Files:**
- Create: `frontend/src/components/SearchBox.tsx`
- Create: `frontend/src/components/SitePanel.tsx`
- Create: `frontend/src/components/SitePanel.test.tsx`

**Interfaces:**
- Consumes: `searchPlaces` (Task 6), `SiteSelectionState`/`SiteStatus` (Task 8).
- Produces: `SearchBoxProps { onResultSelected: (lat: number, lon: number) => void }`, default export `SearchBox`; `SitePanelProps { state: SiteSelectionState; onAnalyze: () => void; onRetry: () => void }`, default export `SitePanel`.

- [ ] **Step 1: Write the failing test for SitePanel**

Create `frontend/src/components/SitePanel.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { SiteSelectionState } from '../hooks/useSiteSelection'
import SitePanel from './SitePanel'

const baseState: SiteSelectionState = {
  status: 'idle',
  village: null,
  elevation: null,
  errorMessage: null,
  lastPoint: null,
}

describe('SitePanel', () => {
  it('shows a prompt when idle', () => {
    render(<SitePanel state={baseState} onAnalyze={vi.fn()} onRetry={vi.fn()} />)
    expect(screen.getByText(/click anywhere/i)).toBeInTheDocument()
  })

  it('shows a locating indicator', () => {
    render(<SitePanel state={{ ...baseState, status: 'locating' }} onAnalyze={vi.fn()} onRetry={vi.fn()} />)
    expect(screen.getByText(/locating/i)).toBeInTheDocument()
  })

  it('shows the village name and an Analyze button once located', () => {
    const village = { id: 'v1', name: 'Bhilai', state: 'Chhattisgarh', district: 'Durg', lat: 21.19, lon: 81.3 }
    render(
      <SitePanel state={{ ...baseState, status: 'located', village }} onAnalyze={vi.fn()} onRetry={vi.fn()} />,
    )
    expect(screen.getByText('Bhilai')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /analyze this site/i })).toBeInTheDocument()
  })

  it('calls onAnalyze when the button is clicked', async () => {
    const village = { id: 'v1', name: 'Bhilai', state: 'Chhattisgarh', district: 'Durg', lat: 21.19, lon: 81.3 }
    const onAnalyze = vi.fn()
    render(<SitePanel state={{ ...baseState, status: 'located', village }} onAnalyze={onAnalyze} onRetry={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: /analyze this site/i }))

    expect(onAnalyze).toHaveBeenCalledOnce()
  })

  it('shows elevation stats once analyzed', async () => {
    const village = { id: 'v1', name: 'Bhilai', state: 'Chhattisgarh', district: 'Durg', lat: 21.19, lon: 81.3 }
    const elevation = {
      village_id: 'v1',
      bbox: { min_lon: 81.2, min_lat: 21.1, max_lon: 81.4, max_lat: 21.3 },
      min_elevation: 250,
      max_elevation: 300,
      contours: [],
    }
    render(
      <SitePanel
        state={{ ...baseState, status: 'analyzed', village, elevation }}
        onAnalyze={vi.fn()}
        onRetry={vi.fn()}
      />,
    )
    // The numbers count up via requestAnimationFrame rather than snapping
    // in (see the spec's animation section), so this needs to wait for the
    // animation to settle rather than assert synchronously.
    await waitFor(() => expect(screen.getByText(/250/)).toBeInTheDocument(), { timeout: 1000 })
    expect(screen.getByText(/300/)).toBeInTheDocument()
  })

  it('shows the error message and a retry button on error', async () => {
    const onRetry = vi.fn()
    render(
      <SitePanel
        state={{ ...baseState, status: 'error', errorMessage: "couldn't identify a site here" }}
        onAnalyze={vi.fn()}
        onRetry={onRetry}
      />,
    )
    expect(screen.getByText(/couldn't identify a site here/i)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test`
Expected: FAIL — `Failed to resolve import "./SitePanel"`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/components/SitePanel.tsx`:

```tsx
import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, Loader2, MapPin, Mountain } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { SiteSelectionState } from '../hooks/useSiteSelection'

interface SitePanelProps {
  state: SiteSelectionState
  onAnalyze: () => void
  onRetry: () => void
}

// Counts up to `target` over `durationMs` instead of snapping straight to
// the final number, per the spec's animation section.
function useCountUp(target: number, durationMs = 600): number {
  const [value, setValue] = useState(0)

  useEffect(() => {
    let frame: number
    const start = performance.now()
    function tick(now: number) {
      const progress = Math.min((now - start) / durationMs, 1)
      setValue(Math.round(target * progress))
      if (progress < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [target, durationMs])

  return value
}

export default function SitePanel({ state, onAnalyze, onRetry }: SitePanelProps) {
  const minElevation = useCountUp(state.elevation ? Math.round(state.elevation.min_elevation) : 0)
  const maxElevation = useCountUp(state.elevation ? Math.round(state.elevation.max_elevation) : 0)

  return (
    <div className="flex h-full w-80 flex-col gap-4 bg-slate-900/90 p-6 text-slate-100 backdrop-blur">
      <h1 className="font-display text-xl font-semibold">HydroSage</h1>

      <AnimatePresence mode="wait">
        {state.status === 'idle' && (
          <motion.p
            key="idle"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="text-sm text-slate-400"
          >
            Click anywhere on the map to select a site, or search for a place above.
          </motion.p>
        )}

        {state.status === 'locating' && (
          <motion.div
            key="locating"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex items-center gap-2 text-sm text-slate-300"
          >
            <Loader2 className="h-4 w-4 animate-spin" />
            Locating...
          </motion.div>
        )}

        {(state.status === 'located' || state.status === 'analyzing' || state.status === 'analyzed') &&
          state.village && (
            <motion.div
              key="located"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="flex flex-col gap-3"
            >
              <div className="flex items-start gap-2">
                <MapPin className="mt-1 h-4 w-4 text-sky-400" />
                <div>
                  <p className="font-medium">{state.village.name}</p>
                  <p className="text-xs text-slate-400">
                    {state.village.district}, {state.village.state}
                  </p>
                </div>
              </div>

              {state.status === 'located' && (
                <button
                  type="button"
                  onClick={onAnalyze}
                  className="rounded-md bg-sky-500 px-3 py-2 text-sm font-medium text-white hover:bg-sky-400"
                >
                  Analyze this site
                </button>
              )}

              {state.status === 'analyzing' && (
                <div className="flex items-center gap-2 text-sm text-slate-300">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Fetching elevation...
                </div>
              )}

              {state.status === 'analyzed' && state.elevation && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex items-center gap-2 rounded-md bg-slate-800 p-3 text-sm"
                >
                  <Mountain className="h-4 w-4 text-emerald-400" />
                  <span>
                    Elevation {minElevation}m &ndash; {maxElevation}m
                  </span>
                </motion.div>
              )}
            </motion.div>
          )}

        {state.status === 'error' && (
          <motion.div
            key="error"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col gap-2 rounded-md bg-red-950/60 p-3 text-sm text-red-200"
          >
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4" />
              {state.errorMessage}
            </div>
            <button
              type="button"
              onClick={onRetry}
              className="self-start rounded-md bg-red-800 px-3 py-1 text-xs font-medium hover:bg-red-700"
            >
              Retry
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
```

Create `frontend/src/components/SearchBox.tsx`:

```tsx
import { Search } from 'lucide-react'
import { useState } from 'react'
import { searchPlaces } from '../api/client'

interface SearchBoxProps {
  onResultSelected: (lat: number, lon: number) => void
}

export default function SearchBox({ onResultSelected }: SearchBoxProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<{ display_name: string; lat: number; lon: number }[]>([])

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!query.trim()) return
    const found = await searchPlaces(query)
    setResults(found)
  }

  return (
    <div className="absolute left-1/2 top-4 z-[1000] w-96 -translate-x-1/2">
      <form
        onSubmit={handleSubmit}
        className="flex items-center gap-2 rounded-md bg-slate-900/90 px-3 py-2 text-slate-100 shadow-lg backdrop-blur"
      >
        <Search className="h-4 w-4 text-slate-400" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search a place..."
          className="w-full bg-transparent text-sm outline-none placeholder:text-slate-500"
        />
      </form>
      {results.length > 0 && (
        <ul className="mt-1 rounded-md bg-slate-900/95 text-sm text-slate-100 shadow-lg">
          {results.map((result) => (
            <li key={`${result.lat}-${result.lon}`}>
              <button
                type="button"
                onClick={() => {
                  onResultSelected(result.lat, result.lon)
                  setResults([])
                  setQuery(result.display_name)
                }}
                className="block w-full px-3 py-2 text-left hover:bg-slate-800"
              >
                {result.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test`
Expected: PASS (6 `SitePanel` tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/SitePanel.tsx frontend/src/components/SitePanel.test.tsx frontend/src/components/SearchBox.tsx
git commit -m "Add SitePanel (staged status UI) and SearchBox components"
```

---

## Task 11: Wire it all together in `App.tsx`

**Files:**
- Modify: `frontend/src/App.tsx` (full replace)

**Interfaces:**
- Consumes: `useGeolocation` (Task 7), `useSiteSelection` (Task 8), `MapView` (Task 9), `SitePanel`/`SearchBox` (Task 10).

- [ ] **Step 1: Write the component**

Replace the full contents of `frontend/src/App.tsx`:

```tsx
import MapView from './components/MapView'
import SearchBox from './components/SearchBox'
import SitePanel from './components/SitePanel'
import { useGeolocation } from './hooks/useGeolocation'
import { useSiteSelection } from './hooks/useSiteSelection'

function App() {
  const { position } = useGeolocation()
  const { state, selectPoint, analyze } = useSiteSelection()

  const markerPosition = state.village ? { lat: state.village.lat, lon: state.village.lon } : null
  const contours = state.elevation?.contours ?? []

  return (
    <div className="relative flex h-full w-full">
      <div className="relative flex-1">
        <MapView center={position} markerPosition={markerPosition} contours={contours} onMapClick={selectPoint} />
        <SearchBox onResultSelected={selectPoint} />
      </div>
      <SitePanel
        state={state}
        onAnalyze={analyze}
        onRetry={() => state.lastPoint && selectPoint(state.lastPoint.lat, state.lastPoint.lon)}
      />
    </div>
  )
}

export default App
```

(`onRetry` re-attempts `state.lastPoint` — the point that actually failed — rather than the browser's current geolocation, which would silently retry the wrong location if the user had clicked somewhere else on the map.)

- [ ] **Step 2: Verify the build**

Run: `npm run build`
Expected: succeeds with no TypeScript errors.

- [ ] **Step 3: Run the full frontend test suite**

Run: `npm run test`
Expected: all tests from Tasks 6, 7, 8, 10 PASS.

- [ ] **Step 4: Manual end-to-end verification**

With the backend running (`docker compose up -d --build`) and the frontend dev server up (`npm run dev` from `frontend/`):
1. Open the app in a browser. Confirm the map loads centered near the browser's geolocation (or Bhilai/Durg if denied).
2. Click anywhere on the map (e.g. near IIT Bhilai). Confirm a marker drops immediately and the panel shows "Locating..." then the resolved place name.
3. Click "Analyze this site." Confirm the panel shows "Fetching elevation..." then real min/max elevation stats, and contour lines appear on the map, revealing progressively rather than all at once.
4. Type a place name into the search box, pick a result, confirm the map recenters and the same flow works from a search-selected point.
5. Note anything that doesn't match this description — this step is the actual acceptance check for the whole plan, not a formality.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "Wire MapView, SearchBox, SitePanel together into the full site-selection flow"
```

---

## Post-plan note

This plan does not cover: catchment delineation, rainfall, pond recommendation, or the land-availability overlay (all still `501` stubs on the backend) — those are explicitly out of scope per the spec's "Non-goals" section and get their own plan once their backend pieces exist, following the same staged-panel pattern established here.

# Architecture

Tracks architecture observations and proposed changes. The handwritten HLD ([docs/private/HLD.txt](private/HLD.txt)) is the starting point for this document, not a commitment — ideas worth keeping are preserved here with rationale; weak assumptions are challenged and replaced, with the change recorded in `DECISIONS.md`.

## Status

Core architecture decided — see `DECISIONS.md` (D-001–D-004). Remaining open item is the land-availability proxy (below).

**Implemented and verified end-to-end** (real PostGIS via Docker Compose, real OpenZenith API, no mocks): `Village` model + migration; seed script (Hiware Bazar, D-004); `ElevationClient` (point, batch, DEM-tile fetch + Terrarium decode + bbox mosaic — confirmed the decoded tile elevations bracket the independently-queried point elevation for the same location); `generate_contours` domain function; `GET /villages` and `GET /villages/{id}/elevation` wired to real data, returning real contour geometry for Hiware Bazar (662–960m range, 310 contour lines). Everything else in the API design is still a `501` stub.

## HLD summary (as proposed)

**Block diagram:** React client → API gateway (FastAPI behind Nginx; auth, rate limiting, routing) → split into a synchronous path (village lookup, cached reports, fast rainfall calls) and an async path (task queue → worker pool for DEM fetch/processing, catchment delineation, runoff computation) → results land in PostgreSQL+PostGIS (vector/relational data) and S3-compatible object storage/MinIO (raw DEM tiles, imagery, generated rasters) → external data APIs (elevation, rainfall, satellite imagery) feed the pipeline.

**Workflow:** user selects a village → system fetches/caches satellite imagery + DEM → generates contour map → user picks a candidate pond point, triggering an async catchment delineation job (D8 flow direction → flow accumulation) → system fetches rainfall data synchronously → once catchment job completes, computes runoff volume → recommends pond depth/dimensions checked against available land → renders all layers on one interactive map.

**Proposed stack:** React + Leaflet/Mapbox GL + Chart.js; FastAPI + Nginx; Redis + Celery/RQ task queue; PostgreSQL + PostGIS; S3-compatible/MinIO object storage; OpenCV + GDAL/Rasterio + pysheds/richdem for geospatial processing; Docker Compose for local orchestration.

**API design:** `GET /villages`, `GET /villages/{id}/elevation`, `GET /villages/{id}/satellite`, `GET /villages/{id}/rainfall` (sync), `POST /villages/{id}/catchment` → job_id, `GET /jobs/{job_id}`, `POST /villages/{id}/recommend` → job_id, `GET /villages/{id}/report`.

**Algorithms:** contour generation via marching squares / OpenCV `findContours` on a quantized elevation raster; catchment delineation via D8 flow-direction + flow accumulation, tracing upstream contributing cells from the candidate point (pysheds/richdem); runoff via SCS Curve Number (primary) with a runoff-coefficient fallback (Rainfall × Catchment Area × Coefficient) when land/soil data is unavailable; pond sizing by targeting storage = runoff volume, back-calculating surface area within a practical depth range, checked against available land.

**Risks the HLD already names:** coarse DEM resolution for small ponds; sparse rainfall data in rural regions; no live government land-record API; catchment delineation being computationally expensive; frontend performance with large overlays; API and workers needing to scale independently.

## Observations / concerns (to resolve before locking the stack)

The core geospatial methodology — D8 delineation, Curve Number runoff with a fallback, PostGIS for spatial data, an async job for the expensive catchment step — is sound and worth keeping. The concern is scale of supporting infrastructure relative to what's actually graded and what a single evaluated web app needs:

1. **Infrastructure weight vs. rubric weight.** The HLD proposes a full microservices-shaped system: API gateway with Nginx, auth, rate limiting; Redis + Celery task queue; a separate worker pool; PostGIS *and* MinIO/S3 as two storage systems; Docker Compose orchestration. "System design and management" is 15/100 of the grade; functionality + terrain/catchment correctness is 55/100. Building and correctly documenting five infrastructure pieces is real time spent that isn't where the marks are, and each piece is a place for something to break before the demo. A single FastAPI process running catchment delineation in a background task/thread pool (still async from the client's perspective — same `POST .../catchment` → `GET /jobs/{id}` contract) can deliver the identical UX with far less to build, deploy, and explain, while leaving room to reintroduce Celery/Redis later if job volume or grading criteria actually demand it.
2. **Two storage systems (PostGIS + MinIO).** Reasonable at production scale; for a bounded demo, local disk (or a `files/` volume) can hold DEM tiles/rasters just as well, with PostGIS handling all vector/relational data. Worth confirming before building both.
3. **WebSocket job-status channel.** Adds a stateful connection to maintain. Polling `GET /jobs/{job_id}` (already in the API design) is simpler and sufficient for a single-user-at-a-time demo tool. Proposing to drop the WebSocket unless there's a specific reason to keep it.
4. **Auth/rate-limiting at the gateway.** Not requested anywhere in the project description, which describes a single-role tool for a village administrator. Proposing to drop this unless the brief is revised.
5. **Contour extraction via OpenCV `findContours`.** That's built for binary/segmented images; elevation contour lines are more naturally produced by marching squares over the raw raster (e.g., `skimage.measure.find_contours`, or GDAL's contour generation). Not a blocker now — worth deciding at implementation time, noted here so it isn't lost.

Resolved by D-001: keep Celery+Redis+worker pool, PostGIS, object storage, Docker Compose (each has a concrete technical reason); drop the Nginx auth/rate-limiting gateway and the WebSocket channel (no stated requirement, polling suffices).

## Current architecture

**Client:** React + TypeScript + Vite, `react-leaflet` for the interactive map, Chart.js for rainfall/runoff graphs.

**Backend:** a single FastAPI service (async), organized as a modular monolith rather than a gateway + separate service layer — one deployable unit with clear internal module boundaries, not a network boundary, since there's no stated need to scale or deploy those pieces independently:
- `app/api/` — HTTP routers only (villages, elevation, satellite, rainfall, catchment, jobs, recommend, report). No business logic here.
- `app/domain/` — pure business logic: curve-number/runoff-coefficient runoff estimation, pond sizing, contour generation, catchment-delineation orchestration. No FastAPI, DB, or HTTP imports, so it's unit-testable in isolation and portable if the transport layer ever changes.
- `app/infrastructure/` — PostGIS access (SQLAlchemy 2.0 + GeoAlchemy2), object storage client (MinIO/S3-compatible), external API clients (OpenZenith elevation, rainfall, imagery), Celery task definitions.
- `app/schemas/` — Pydantic request/response models (also drives the auto-generated OpenAPI docs, covering the "API documentation" deliverable).
- Alembic for migrations.
- pytest, with `app/domain/` the priority for coverage since it's the part the 20-mark "terrain and catchment analysis" criterion actually evaluates.

**Async job path:** `POST /villages/{id}/catchment` (and `/recommend`) enqueue a Celery task and return a `job_id` immediately; `GET /jobs/{job_id}` is polled for status/result. Same contract the HLD proposed, minus the WebSocket channel.

**Storage:** PostgreSQL+PostGIS for villages, land polygons, catchment boundaries, pond specs, and job status (vector/relational). MinIO (S3-compatible, local via Docker Compose) for raw DEM tiles, satellite imagery, and generated rasters (large binaries).

**Deployment:** Docker Compose — `api`, `worker` (Celery), `redis`, `postgis`, `minio`. One command to stand up the full stack locally.

**No auth layer.** Single implied user role (village administrator), nothing in the brief to protect against. Revisit if that changes.

## Boundaries and modules

- **Ingestion** (`app/infrastructure/*_client.py`) — fetches/caches elevation (OpenZenith), rainfall, and satellite imagery from external APIs. Owns retry/caching; knows nothing about runoff or pond sizing.
- **Terrain processing** (`app/domain/terrain.py`) — DEM → contour geometry.
- **Catchment delineation** (`app/domain/catchment.py`, run via Celery) — D8 flow direction/accumulation → watershed boundary from a candidate point.
- **Runoff & recommendation** (`app/domain/runoff.py`, `app/domain/pond.py`) — Curve Number/coefficient runoff volume, pond depth/dimensions checked against available land. Pure functions over already-fetched data; no I/O.
- **Presentation** (`app/api/`, frontend) — combines the above into the overlay view and report. Owns no business rules.

## Changes from the original HLD

| Change | Reason | Date |
|---|---|---|
| Dropped Nginx gateway + auth/rate-limiting | No stated requirement for authentication or multi-tenancy (D-001) | 2026-08-25 |
| Dropped WebSocket job-status channel, kept polling | Simpler, sufficient for single-user demo; can be added later without breaking the API (D-001) | 2026-08-25 |
| Confirmed OpenZenith as the elevation API | User verified it's a real, working API (D-002) | 2026-08-25 |
| Frontend: added TypeScript to the HLD's React + Leaflet + Chart.js | Type safety for code-quality criterion; no functional change | 2026-08-25 |

## External API surface

Originally built entirely against OpenZenith (project description named it as the elevation source, and it turned out to cover far more — see D-003). Moved off it per D-005 after it proved flaky in practice (a full outage, then intermittent 503s even after "recovering") — replaced with three separate, individually well-established services instead of one convenient aggregator:

| Need | Provider | Endpoint | Notes |
|---|---|---|---|
| DEM raster (area) | OpenTopography | `GET /API/globaldem?demtype=COP30&south&north&east&west&outputFormat=GTiff&API_Key=...` | Returns a GeoTIFF directly for a bbox — read with `rasterio` (already a dependency), no tile math needed. Free tier: 50 calls/day (200/day academic), workable because each site's DEM is cached in MinIO after first fetch. Verified live: 299×475 raster, EPSG:4326, 662.8–959.2m for the Hiware Bazar bbox — closely matches OpenZenith's figures for the same area. |
| Village/place geocoding (both directions) | Nominatim | `GET /search` / `GET /reverse` | Direct — OpenZenith was itself just proxying this. No key; usage policy requires a descriptive `User-Agent` and ~1 request/sec. Verified live for both a forward query and reverse-geocoding the Bhilai/Durg default map center. |
| Satellite imagery | Esri World Imagery | Standard XYZ tile URL | Needs no backend proxy at all — a Leaflet tile-layer URL on the frontend directly. |
| Land-use data (future — land-availability proxy) | OSM Overpass API | `POST https://overpass-api.de/api/interpreter` | Direct — same reasoning as geocoding; feeds open question #1 below, not yet built. |

`app/infrastructure/elevation_client.py` wraps OpenTopography; `app/infrastructure/geocoding_client.py` wraps Nominatim. Both stay thin per D-002/D-005's rationale — swappable again if needed without touching domain logic.

## Open questions

1. Government-land proxy dataset — no live API exists (HLD's own risk list). Implementation path: OSM Overpass, querying land-use polygons filtered to non-built-up, non-water land within a village's bounds, designed to be swappable for an official source later, per the HLD's own mitigation plan.
2. ~~Village boundary/list source~~ — superseded by the map-first, click-anywhere design (`docs/superpowers/specs/2026-08-26-village-map-selection-design.md`): no pre-seeded list at all, villages are created on demand from wherever the user selects on the map. Hiware Bazar (D-004) remains seeded as a working example.
3. ~~Satellite imagery source~~ — resolved: Esri World Imagery (D-005).

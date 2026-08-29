# Architecture

Tracks architecture observations and proposed changes. The handwritten HLD ([docs/private/HLD.txt](private/HLD.txt)) is the starting point for this document, not a commitment — ideas worth keeping are preserved here with rationale; weak assumptions are challenged and replaced, with the change recorded in `DECISIONS.md`.

## Status

Core architecture decided — see `DECISIONS.md` (D-001–D-006). The full pipeline described in the HLD's own workflow (terrain → catchment → rainfall → runoff → pond sizing, checked against land availability, overlaid in one view) is built and verified against real data on both input paths (a live DEM fetch from a map click, and an uploaded contour KML). Land-availability (open question #1 below, historically) is resolved. Remaining gaps are deliverables, not architecture: the Phase 1 report, and a live deployment — see `docs/PROJECT_STATUS.md` for exact current state.

## HLD summary (as proposed)

**Block diagram:** React client → API gateway (FastAPI behind Nginx; auth, rate limiting, routing) → split into a synchronous path (village lookup, cached reports, fast rainfall calls) and an async path (task queue → worker pool for DEM fetch/processing, catchment delineation, runoff computation) → results land in PostgreSQL+PostGIS (vector/relational data) and S3-compatible object storage/MinIO (raw DEM tiles, imagery, generated rasters) → external data APIs (elevation, rainfall, satellite imagery) feed the pipeline.

**Workflow:** user selects a village → system fetches/caches satellite imagery + DEM → generates contour map → user picks a candidate pond point, triggering an async catchment delineation job (D8 flow direction → flow accumulation) → system fetches rainfall data synchronously → once catchment job completes, computes runoff volume → recommends pond depth/dimensions checked against available land → renders all layers on one interactive map.

**Proposed stack:** React + Leaflet/Mapbox GL + Chart.js; FastAPI + Nginx; Redis + Celery/RQ task queue; PostgreSQL + PostGIS; S3-compatible/MinIO object storage; OpenCV + GDAL/Rasterio + pysheds/richdem for geospatial processing; Docker Compose for local orchestration.

**API design:** `GET /villages`, `GET /villages/{id}/elevation`, `GET /villages/{id}/satellite`, `GET /villages/{id}/rainfall` (sync), `POST /villages/{id}/catchment` → job_id, `GET /jobs/{job_id}`, `POST /villages/{id}/recommend` → job_id, `GET /villages/{id}/report`.

**Algorithms:** contour generation via marching squares / OpenCV `findContours` on a quantized elevation raster; catchment delineation via D8 flow-direction + flow accumulation, tracing upstream contributing cells from the candidate point (pysheds/richdem); runoff via SCS Curve Number (primary) with a runoff-coefficient fallback (Rainfall × Catchment Area × Coefficient) when land/soil data is unavailable; pond sizing by targeting storage = runoff volume, back-calculating surface area within a practical depth range, checked against available land.

**Risks the HLD already names:** coarse DEM resolution for small ponds; sparse rainfall data in rural regions; no live government land-record API; catchment delineation being computationally expensive; frontend performance with large overlays; API and workers needing to scale independently.

## Observations / concerns (as of initial planning — see "Current architecture" below for what actually shipped)

The core geospatial methodology — D8 delineation, Curve Number runoff with a fallback, PostGIS for spatial data — was sound and worth keeping. The concern at the time was scale of supporting infrastructure relative to what's actually graded:

1. **Infrastructure weight vs. rubric weight.** The HLD proposes a full microservices-shaped system: API gateway with Nginx, auth, rate limiting; Redis + Celery task queue; a separate worker pool; PostGIS *and* MinIO/S3 as two storage systems; Docker Compose orchestration. "System design and management" is 15/100 of the grade; functionality + terrain/catchment correctness is 55/100.
2. **Two storage systems (PostGIS + MinIO).** Kept both in the end, each doing a job the other doesn't fit (see Current architecture) — not the local-disk simplification originally floated.
3. **WebSocket job-status channel.** Dropped — no async job path was ever built (D-006), so this question is moot rather than resolved.
4. **Auth/rate-limiting at the gateway.** Not requested anywhere in the project description. Dropped, never revisited.
5. **Contour extraction.** Settled on `skimage.measure.find_contours` (marching squares over the raw raster), not OpenCV — the right call, unchanged since.

Resolved by D-001 (2026-08-25): keep infrastructure with a concrete technical reason, drop the rest. Superseded in part by D-006 (2026-08-30): the Celery/worker piece never got a real justification in practice and was dropped; Redis was kept anyway, repurposed as the catchment-result cache.

## Current architecture

**Client:** React + TypeScript + Vite, `react-leaflet` for the interactive map, Tailwind CSS v4, Framer Motion for animation, `lucide-react` for icons, Vitest + Testing Library. Chart.js was in the original HLD's proposed stack but was never actually used — there's no chart in the app; rainfall/runoff are presented as numbers and a color-ramp contour legend, not a graph. Worth adding if the report benefits from one, not currently planned.

**Backend:** a single FastAPI service (synchronous request handling throughout — see "No async job path" below), organized as a modular monolith with clear internal module boundaries, not a network boundary:
- `app/api/` — HTTP routers only (villages, rainfall, recommend, geocode, analyze_contour). `satellite.py` and `report.py` remain `501` stubs: satellite imagery is served client-side directly from Esri's tile service (no backend involvement needed), and no report-generation endpoint has been built (the Phase 1 report is a separate written deliverable, not an API route). No business logic in this layer.
- `app/domain/` — pure business logic, no I/O: `terrain.py` (contour generation, with auto-picked round intervals and light smoothing), `catchment.py` (D8 flow routing via pysheds — samples a spread of local flow-accumulation maxima and picks the best-ranked candidate whose catchment area falls in a realistic range, rather than the single global maximum), `rainfall.py` (daily → monthly/annual aggregation), `runoff.py` (runoff-coefficient method), `pond.py` (depth/surface-area sizing), `land_availability.py` (exclusion-based available-land estimate from OSM features). Each is independently unit-tested — this is the layer the 20-mark "terrain and catchment analysis" criterion actually evaluates.
- `app/services/` — a layer the original design didn't anticipate needing: orchestration that does real I/O across multiple domain functions and infrastructure clients for one use case, and is shared by more than one endpoint. Currently just `recommendation.py` (`compute_recommendation_fields`): rainfall → runoff → pond sizing → land-availability, used by both `POST /villages/{id}/recommend` (a village's stored location) and `POST /analyzeContour` (an uploaded survey's own bbox centroid — there's no "village" row to key off). Not pure enough for `domain/` (it calls `RainfallClient`/`LandUseClient`), not an HTTP concern for `api/`. Each piece it orchestrates is unit-tested on its own; this layer itself is verified live via its two callers, same as `api/`'s own endpoint-level orchestration always has been.
- `app/infrastructure/` — PostGIS access (SQLAlchemy 2.0 + GeoAlchemy2), external API clients (`elevation_client.py`, `geocoding_client.py`, `rainfall_client.py`, `land_use_client.py`), KML parsing (`kml_parser.py`), and two caches: `dem_cache.py` (MinIO, raw DEM GeoTIFF bytes keyed by village) and `catchment_cache.py` (Redis, computed `CatchmentResult` keyed by village) — see "Caching" below.
- `app/schemas/` — Pydantic request/response models, also driving the auto-generated OpenAPI docs (the "API documentation" deliverable). Shared-field base models (`CatchmentFieldsOut`, `RecommendationFieldsOut`) avoid duplicating response shapes across the two endpoints that independently compute the same things.
- Alembic for migrations — applied automatically on every container start (`alembic upgrade head` before `uvicorn` in `backend/Dockerfile`'s `CMD`), not a manual step. Found the hard way: a fresh Postgres volume under Docker had no schema at all until this was added.

**No async job path.** The HLD's `POST .../catchment` → `job_id` → `GET /jobs/{id}` polling contract was never built — every endpoint (`/elevation`, `/recommend`, `/analyzeContour`) runs its full computation inline and returns the result directly. This has held up fine at the scale this app actually runs at (worst observed response time across the whole build: ~22s, and that was an external API degrading, not the app's own computation). See D-006 for the full reasoning and what got dropped as a result (`app/api/catchment.py`, `app/api/jobs.py`, the `worker` Docker Compose service).

**Caching.** Two caches, both added only after a concrete, measured cost was identified — not speculatively:
- **DEM cache** (MinIO) protects OpenTopography's 50-calls/day free tier. Verified: 14.7s cold fetch → 1.5s cached, byte-identical result.
- **Catchment-result cache** (Redis) avoids re-running the D8 pipeline when two different endpoints analyze the same site (e.g. "Analyze this site" then "Get pond recommendation" for the same village). Verified via direct Redis inspection that both endpoints share one computed result.

**Storage:** PostgreSQL+PostGIS for villages (vector/relational data — the only thing that needs a real spatial database). MinIO (S3-compatible) for the DEM cache specifically — large binaries that don't belong as relational rows. Redis for the catchment-result cache — small JSON, short TTL, a different shape of caching need than MinIO's.

**Deployment:** Docker Compose — `postgis`, `redis`, `minio`, `api`, `frontend` (nginx serving a static Vite build; `frontend/Dockerfile` is new — the original HLD's client had no containerization plan). All services get `restart: unless-stopped`. CORS origins and the two host ports are environment-configured (`CORS_ALLOWED_ORIGINS`, `API_PORT`/`FRONTEND_PORT`), not hardcoded — a hardcoded `localhost`-only CORS allowlist already caused one real outage this project (D-005) and would have recurred at deployment otherwise.

**No auth layer.** Single implied user role (village administrator), nothing in the brief to protect against. Unchanged since D-001.

## Boundaries and modules

- **Ingestion** (`app/infrastructure/*_client.py`) — fetches elevation (OpenTopography), geocoding (Nominatim), rainfall (Open-Meteo), and land-use exclusion features (OSM Overpass) from external APIs. Owns retry/timeout behavior; knows nothing about runoff or pond sizing.
- **Caching** (`app/infrastructure/dem_cache.py`, `catchment_cache.py`) — sits in front of the ingestion/computation it protects, never able to fail the request it's optimizing (every failure mode degrades to "recompute", never raises).
- **Terrain processing** (`app/domain/terrain.py`) — DEM → contour geometry.
- **Catchment delineation** (`app/domain/catchment.py`) — D8 flow direction/accumulation → a realistically-scaled watershed boundary and pond site. Run inline, not via a job queue (see "No async job path").
- **Rainfall, runoff, and pond sizing** (`app/domain/rainfall.py`, `runoff.py`, `pond.py`) — pure functions over already-fetched data; no I/O.
- **Land availability** (`app/domain/land_availability.py`) — pure geometry (shapely) over already-fetched OSM features; no I/O.
- **Recommendation orchestration** (`app/services/recommendation.py`) — the one layer that does cross-cutting I/O across the above, shared by two endpoints. See its own section above.
- **Presentation** (`app/api/`, frontend) — combines the above into the overlay view. Owns no business rules.

## Changes from the original HLD

| Change | Reason | Date |
|---|---|---|
| Dropped Nginx gateway + auth/rate-limiting | No stated requirement for authentication or multi-tenancy (D-001) | 2026-08-25 |
| Dropped WebSocket job-status channel, kept polling | Simpler, sufficient for single-user demo; moot once the job path itself was dropped (D-006) | 2026-08-25 |
| Confirmed OpenZenith as the elevation API, then moved off it | User verified OpenZenith was real; it then proved unreliable in practice, replaced with OpenTopography + Nominatim + Esri (D-005) | 2026-08-25 / 2026-08-26 |
| Frontend: added TypeScript to the HLD's React + Leaflet + Chart.js | Type safety for code-quality criterion; Chart.js itself was never actually used | 2026-08-25 |
| Dropped the Celery worker and async job contract entirely | Never wired to anything; every endpoint ran its computation inline instead and held up fine (D-006) | 2026-08-30 |
| Added `app/services/` as a new module tier | Two endpoints needed the same rainfall/runoff/pond/land orchestration; neither `domain/` (has I/O) nor `api/` (shared business logic, not HTTP concern) fit | 2026-08-30 |
| Catchment site selection rewritten | The original "single global flow-accumulation maximum" approach claimed 20-36% of any analyzed area regardless of input; rewritten to search for a realistically-scaled site instead | 2026-08-30 |

## External API surface

Originally built entirely against OpenZenith (project description named it as the elevation source, and it turned out to cover far more — see D-003). Moved off it per D-005 after it proved flaky in practice — replaced with individually well-established, single-purpose services:

| Need | Provider | Notes |
|---|---|---|
| DEM raster (area) | OpenTopography (`COP30`) | Returns a GeoTIFF directly for a bbox, read with `rasterio`. Free tier: 50 calls/day — protected by `dem_cache.py` (MinIO), so the limit applies to genuinely new sites, not repeat interactions. |
| Village/place geocoding (both directions) | Nominatim | No key; usage policy requires a descriptive `User-Agent` and ~1 request/sec. |
| Historical rainfall | Open-Meteo (archive API, ERA5 reanalysis) | No key. Chosen over NASA POWER (also free, also named in the brief) for finer resolution (~9-25km vs. ~50km). |
| Land-use exclusion features | OSM Overpass API | No key, but some public mirrors reject a generic/bot-like `User-Agent` (403) — `land_use_client.py` sends the same descriptive one Nominatim requires. Best-effort: a failed lookup degrades the recommendation's land-availability fields to `null` rather than failing the whole request. |
| Satellite imagery | Esri World Imagery | Standard XYZ tile URL, no backend proxy — a Leaflet tile-layer URL on the frontend directly. |

## Open questions

1. ~~Government-land proxy dataset~~ — resolved: OSM Overpass, exclusion-based (subtract mapped buildings/roads/water/residential/industrial zones from the bbox, treat the remainder as available). An approximation, not a survey — see `domain/land_availability.py`'s own docstring for the honest limitations.
2. ~~Village boundary/list source~~ — superseded by the map-first, click-anywhere design: no pre-seeded list at all, villages are created on demand from wherever the user selects on the map.
3. ~~Satellite imagery source~~ — resolved: Esri World Imagery (D-005).
4. **Runoff method: coefficient vs. Curve Number.** Still the coefficient fallback (see `domain/runoff.py`'s own docstring), since real Curve Number needs a soil hydrologic group per cell that this app doesn't have. `land_availability.py`'s OSM data gives some land-cover signal now, but not soil type — upgrading this is a real, not-yet-started piece of work, not just a documentation gap.
5. **Deployment target.** Nothing is live publicly yet. A VM with SSH+sudo access is the planned target (Docker Compose, per "Deployment" above); the actual deployment hasn't happened as of this writing.

# Decisions

A log of important decisions and their rationale, in the order they were made. Once a decision is recorded here, treat it as current unless a later entry supersedes it.

Each entry:

```
## D-00X: Title
Date: YYYY-MM-DD
Status: Proposed | Accepted | Superseded by D-00Y

Context: what prompted this decision.
Decision: what was decided.
Rationale: why, and what alternatives were considered.
```

---

## D-001: Keep the async processing pattern; drop infrastructure without a concrete justification

Date: 2026-08-25
Status: Superseded by D-006 (the Celery/worker part only — the rest of this decision still stands)

**Context:** The HLD proposed a full microservices-shaped system: Nginx API gateway with auth and rate limiting, Redis + Celery task queue, a separate worker pool, PostgreSQL+PostGIS *and* MinIO object storage, WebSocket job-status updates, Docker Compose orchestration. The project description gives a much simpler suggested stack and doesn't ask for auth or multi-tenancy anywhere. Asked the user how much of the HLD's infrastructure to keep; the direction given was to build a genuinely industrial-quality project — good architecture, code, and engineering discipline — not to keep or cut pieces just to match a grading rubric, and that the originally suggested stack isn't binding if something better fits.

**Decision:** Keep every piece of infrastructure that has a concrete technical justification; drop the rest rather than including it for its own sake.

Kept, with reason:
- **Celery + Redis task queue and worker pool** — D8 catchment delineation over a DEM raster is genuinely CPU-heavy (seconds to tens of seconds). Running it inline would block request handling; running it in-process background tasks would fight FastAPI's async event loop. A real task queue is the correct tool here, not over-engineering.
- **PostgreSQL + PostGIS** — villages, land polygons, catchment boundaries, and pond specs are geometry-heavy relational data; PostGIS's spatial types/queries are a direct fit.
- **Object storage (MinIO, S3-compatible) separate from PostGIS** — raw DEM tiles, satellite imagery, and generated rasters are large binaries that don't belong as relational rows. Run locally via Docker Compose so there's no external cloud dependency for development or the demo.
- **Docker Compose** — gives the "installation guide" deliverable a one-command reproducible setup, and is standard practice for a multi-service backend.

Dropped, with reason:
- **Nginx gateway with auth/rate limiting** — no requirement anywhere in the project description for authentication or multi-tenancy; a single village-administrator role is implied throughout. Adding auth invents domain behavior the source material doesn't call for. Revisit if that requirement is later stated explicitly.
- **WebSocket job-status channel** — polling `GET /jobs/{job_id}` (already in the HLD's own API design) gives identical UX for a single-user-at-a-time tool with much less to build and maintain. The job-status endpoint is designed so a WebSocket/SSE channel could be added later without breaking existing clients, if real-time push ever becomes a real need.

**Rationale:** "Industrial-level" is expressed through engineering discipline — clear module boundaries, tests, migrations, structured config, typed code, documentation — not through the number of infrastructure services running. Every kept service earns its place with a specific technical reason tied to this system's actual computational shape; every dropped piece was infrastructure invented ahead of a stated need, which `CLAUDE.md` already directs against ("Do not add dependencies, services, or infrastructure without a concrete reason").

---

## D-002: Elevation data source — OpenZenith

Date: 2026-08-25
Status: Accepted

**Context:** The project description names "OpenZenith" as a suggested elevation API. It didn't match any elevation service known at the time `ARCHITECTURE.md` was first drafted, and was flagged as a possible typo for OpenTopography or Open-Topo-Data.

**Decision:** Use OpenZenith as the elevation data source. The user confirmed it's a real API (`https://openzenith.cyopsys.com/api/elevation?lat=..&lon=..`), offering tile, cURL, JS, and Python access.

**Rationale:** Matches the project description's own suggestion and was confirmed working by the user. The elevation-fetch module should sit behind a thin internal interface (not called directly from domain/business logic) so this can be swapped for OpenTopography or another source later without touching catchment/runoff logic downstream — this was already the plan per the HLD's own risk mitigation for "rainfall API data sparse" and applies equally here.

---

## D-003: Use OpenZenith for elevation, satellite imagery, and OSM land/geocoding data

Date: 2026-08-25
Status: Accepted

**Context:** Investigated OpenZenith's actual API surface (via its OpenAPI spec) rather than assuming it was only the single point-elevation endpoint named in the project description. It turned out to expose far more: `/api/elevation` (point) and `/api/elevation/batch` (up to 2000 points); `/api/dem-tile/{z}/{x}/{y}` (Terrarium-PNG DEM raster tiles, z0–14, Copernicus GLO-30/SRTM-class ~30m source resolution) and `/api/tile/{z}/{x}/{y}` (raw Int16 DEM); `/api/sentinel2/{z}/{x}/{y}` (Sentinel-2 imagery tiles); `/api/overpass` (OpenStreetMap Overpass QL proxy); `/api/geocode` / `/api/reverse-geocode` (Nominatim); `/api/waterways` (OSM rivers/lakes as GeoJSON). No API key required. Verified live: fetched a real DEM tile for the Hiware Bazar area (Ahmednagar/Ahilyanagar district, Maharashtra — see D-004) and confirmed the Terrarium decoding formula (`elevation = R*256 + G + B/256 - 32768`) produces plausible elevation values matching the independently-queried point elevation for the same location.

**Decision:** Use OpenZenith as the single external API for elevation (point, batch, and DEM tiles), satellite imagery (Sentinel-2 tiles), village geocoding, and the OSM Overpass proxy that will back the land-availability approach from `ARCHITECTURE.md`. This resolves `PROJECT_BRIEF.md` open questions #1 (satellite imagery) and materially informs #2 (land-availability proxy) — one API surface instead of three separate integrations (elevation API + imagery API + a raw OSM/Overpass client).

**Rationale:** Fewer external services to integrate, authenticate against, and handle failure modes for, without giving up any capability — each piece (DEM tiles, Sentinel-2, Overpass) is a distinct, independently-documented endpoint behind the same host, not a compromise substitute. Keeps the internal `elevation_client` / future `imagery_client` interfaces thin so any individual piece can still be swapped out later without touching domain logic, per D-002's rationale.

---

## D-004: First demo village — Hiware Bazar, Ahmednagar (Ahilyanagar) district, Maharashtra

Date: 2026-08-25
Status: Accepted

**Context:** `ARCHITECTURE.md` open question #3 (how the village list is sourced) needed a concrete starting point to build and test the pipeline against. No specific region was given in the project description or HLD.

**Decision:** Seed the database with Hiware Bazar as the first demo village (geocoded via OpenZenith: 19.0679874°N, 74.6012297°E).

**Rationale:** It's a real, well-documented Indian watershed-management success story built substantially on the same intervention this project models (check dams, rainwater-harvesting ponds, catchment treatment), which gives the eventual technical report a concrete, verifiable reference case rather than an arbitrary coordinate. Not exclusive — more villages can be seeded the same way once the ingestion pipeline works end-to-end for this one. Revisit if a different region is preferred.

---

## D-005: Move off OpenZenith — elevation to OpenTopography, geocoding to Nominatim, imagery to Esri World Imagery

Date: 2026-08-26
Status: Accepted — supersedes D-002 and the elevation/imagery/geocoding parts of D-003

**Context:** While preparing the implementation plan for the village-selection frontend (`docs/superpowers/specs/2026-08-26-village-map-selection-design.md`), OpenZenith's entire `/api/*` surface — including `/api/elevation` and `/api/dem-tile`, both verified working the day before — started returning 404 across the board (confirmed independently by the user in their own browser, ruling out a client-side or network-specific cause). It later came back, but flaky: retesting `/api/dem-tile` immediately afterward failed 2 of 4 attempts with 503, and `/api/elevation` failed 1 of 4. Its own `/api/health` response reveals why — it's backed by a Hugging Face-hosted dataset repo (`aliasfox/srtm30m-ozt2-v2`, with a documented fallback repo, implying the maintainer already knows it drops out) behind Cloudflare edge functions, not dedicated geospatial serving infrastructure.

**Decision:** Move elevation to OpenTopography's Global DEM API (Copernicus GLO-30, 30m), geocoding to Nominatim's public API directly, and the satellite imagery layer to Esri World Imagery — three separate, individually well-established services instead of one convenient aggregator. Verified all three for real before committing:
- OpenTopography: real API key obtained (user signed up, Registered User tier — sufficient; point-cloud limits and OT+ are irrelevant, we only use the raster Global DEM endpoint). A live call for the same Hiware Bazar bounding box used throughout this project returned a valid GeoTIFF (299×475, EPSG:4326, 662.8–959.2m) that closely matches what OpenZenith returned for the identical bbox the day before (662–960m) — two independent sources agreeing is good evidence both are accurate.
- Nominatim: live forward-geocode ("Hiware Bazar, Maharashtra, India") and reverse-geocode (the Bhilai/Durg default map center) calls both returned correct results.
- Esri World Imagery: a standard, widely-used public XYZ tile service; needs no backend proxy at all, just a Leaflet tile-layer URL on the frontend — simpler than routing imagery through our own API.

**Rationale:** OpenTopography is NSF/San Diego Supercomputer Center-backed infrastructure with over a decade of uptime and use in published research — a materially different reliability class than a single-maintainer hobby aggregator, which matters because elevation/terrain data feeds the two most heavily-weighted grading criteria (functionality + terrain/catchment analysis, 55/100 combined, per `PROJECT_BRIEF.md`). It's also literally the technology the original project description suggested, which strengthens the eventual technical report. The Global DEM API returns a GeoTIFF directly for a bounding box, which `rasterio` (already a dependency) reads with georeferencing built in — simpler than OpenZenith's tile-fetch-and-Terrarium-decode approach, not just more reliable. The trade-off is a daily rate limit (50 calls/day on the free tier); this is workable because each analyzed site's DEM gets cached in MinIO after first fetch (already the plan per D-001), so the limit applies to *new* sites per day, not total interactions. The broader principle, extended consistently to imagery and geocoding too: several proven, single-purpose, institutionally-backed services beat one convenient but unproven all-in-one aggregator, especially for something that can't be fully retested right before it's graded.

**Impact:** `app/infrastructure/elevation_client.py` gets rewritten against OpenTopography instead of OpenZenith (same external interface shape — this swap is exactly why D-002 argued for a thin, swappable client in the first place). A new `app/infrastructure/geocoding_client.py` targets Nominatim directly. The already-working `GET /villages/{id}/elevation` endpoint and its tests get updated accordingly. `docs/ARCHITECTURE.md`'s "External API surface" section and the village-selection spec are updated to match.

---

## D-006: Drop the Celery worker; keep Redis for a different reason than originally planned

Date: 2026-08-30
Status: Accepted — supersedes the Celery/worker part of D-001

**Context:** D-001 kept Celery + Redis + a worker pool specifically because D8 catchment delineation is CPU-heavy and running it inline would block request handling. In practice, every endpoint built since (`GET /villages/{id}/elevation`, `POST /villages/{id}/recommend`, `POST /analyzeContour`) calls `analyze_catchment` synchronously and inline, and it's been fine — the slowest observed request across the whole session was ~22s (with a degrading external API in the mix, not the catchment computation itself), which is acceptable for a single-user demo tool with no concurrent load. The `worker` service in `docker-compose.yml` and the `POST /villages/{id}/catchment` / `GET /jobs/{job_id}` stub routes were never actually wired to anything — they sat as unused scaffolding from the original async design for the whole project. This surfaced concretely while preparing a real deployment: running an unused Celery worker container on someone else's shared VM is a cost with no corresponding benefit.

**Decision:** Drop the `worker` service and the `POST /villages/{id}/catchment` / `GET /jobs/{job_id}` stub routers (`app/api/catchment.py`, `app/api/jobs.py`) — dead code for a design that was never built. Keep Redis, but for a different, concrete reason than D-001's: it's now the backing store for `CatchmentCache` (`app/infrastructure/catchment_cache.py`), caching computed catchment results so two endpoints analyzing the same site don't redundantly redo the D8 pipeline. `app/celery_app.py` and the `celery` dependency are left in place for now (harmless, not deployed) rather than deleted, since removing a dependency is a separate, smaller cleanup with no urgency.

**Rationale:** D-001 itself already established the right principle — keep infrastructure with a concrete technical justification, drop the rest rather than including it for its own sake. Nothing has ever given Celery a concrete justification in this codebase; every actual computation, including the CPU-heavy D8 step D-001 was worried about, runs inline and has been fast enough throughout. Revisit if real concurrent usage ever makes inline computation a genuine bottleneck — the async job-status contract (`POST .../catchment` → `job_id`, `GET /jobs/{id}`) can be reintroduced without breaking existing clients if that happens, same as D-001 originally noted for the WebSocket-vs-polling call.

**Impact:** `docker-compose.yml`'s `worker` service removed; `api`/`postgis`/`redis`/`minio` given `restart: unless-stopped` for deployment. `app/main.py` no longer imports or registers the `catchment`/`jobs` routers. No test or frontend code referenced either removed route.

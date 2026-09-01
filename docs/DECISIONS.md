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

---

## D-007: Pond sizing — demand-driven (100% of annual runoff) to supply-driven (terrain flood-fill capacity)

Date: 2026-09-01
Status: Accepted

**Context:** `domain/pond.py`'s `recommend_pond_dimensions` targeted a storage volume equal to 100% of one year's estimated catchment runoff (`domain/runoff.py`'s coefficient method), then back-solved a flat square footprint at each candidate depth. Once depression-preferred site selection (see the catchment/pond-volume improvements plan, 2026-09-01) started reliably landing on realistically-sized catchments near the top of the documented 1-50ha range, this produced reservoir-scale pond dimensions in the live app — e.g. a 213.7m × 213.7m × 2m pond (~91,000 m³) for a 25.8ha catchment — confirmed by the user testing the deployed app directly. The catchment area itself was not the problem (well within the documented realistic range); the demand target (capture 100% of annual runoff from tens of hectares in a single small pond) was.

**Decision:** Switch the app's primary pond-sizing path to supply-driven: each candidate depth's volume is that depth's own real terrain-holding capacity (`domain/catchment.py`'s flood-fill, `achievable_volume_m3_by_depth`), computed via a new `domain/pond.py` function, `size_pond_from_terrain_capacity`. The existing `recommend_pond_dimensions` (demand-target-driven) is kept, unmodified, as an available utility for a target-volume use case, but is no longer how the app's own recommendation is sized. The `PondOptionOut` schema's `fits_terrain_capacity` boolean (added in the prior plan, now vacuous by construction once sizing IS terrain capacity) is replaced with `runoff_capture_ratio`, a continuous stat showing this depth's terrain capacity as a multiple of a typical year's catchment runoff (unbounded — a value above 1.0 means the terrain could hold more than a year's runoff).

**Rationale:** A sibling reference project (`virtualvasu/contour-detection-service`) independently arrived at the same supply-driven model — flood-fill the real terrain, cap at a realistic depth, size the pond to what the land can actually hold — and never produces reservoir-scale numbers regardless of catchment area, since the bound is physical, not an arbitrary capture target. This matches the user's own explicit priority throughout this project: physical/hydrological correctness over convenient implementation. Site selection itself is unaffected by this decision — only how the already-selected site's pond gets sized.

**Impact:** `domain/pond.py` gains `size_pond_from_terrain_capacity`; `recommend_pond_dimensions`/`PondRecommendation` and their existing tests are unchanged. `services/recommendation.py` calls the new function instead of the old one; its own public signature is unchanged, so neither `api/recommend.py` nor `api/analyze_contour.py` needed changes. `schemas/recommend.py`'s `PondOptionOut` loses `fits_terrain_capacity`, gains `runoff_capture_ratio: float | None`. No frontend changes (the new field isn't rendered yet, same deferral as the prior plan).

---

## D-008: Exclude KML interpolation artifacts from depression detection

Date: 2026-09-01
Status: Accepted

**Context:** D-006's final review flagged, and parked as unconfirmed, a risk in `_find_depressions` (added for depression-preferred site selection): its non-strict `elevation <= local_min` check can flag a large flat region as a "depression" even when that region is nearest-neighbor-extrapolated filler (`kml_parser.py`'s fallback for grid cells outside a KML's own surveyed convex hull), not real terrain. This change was originally made in the belief that it explained the degenerate 0m × 0m pond the KMZ flow was returning; **that belief was wrong, and this change did not fix that bug** — see D-009 for the actual root cause, found by instrumenting the pipeline afterwards. Measured on the real sample KML, the filter changes nothing at all: `_find_depressions` returns the same 7867 depression cells with or without it, because 96.95% of that grid is genuinely interpolated and the selected site was real surveyed terrain, not filler.

**Status note:** kept deliberately despite not fixing the bug it was written for. The failure mode it guards is physically real — a sparse or L-shaped survey leaves large extrapolated regions, and nearest-neighbor fill makes those perfectly flat, which is exactly the shape `_find_depressions` cannot distinguish from a genuine basin. It is small, tested, has no effect on the live-DEM flow, and cost nothing further to keep once written. But it is unproven against real data, and a future reader should not mistake it for a fix that was ever observed to change an outcome.

**Decision:** `kml_parser.py`'s `parse_contour_kml` now returns a fourth value, `valid_mask: np.ndarray` — True where a grid cell came from genuine linear interpolation of surveyed contour points, False where it was filled by the nearest-neighbor fallback. `domain/catchment.py`'s `analyze_catchment` and `_find_depressions` both gain an optional `valid_mask` parameter (default `None`, meaning "trust every cell" — the live-DEM flow's existing behavior, since a fetched DEM has no equivalent extrapolated-filler concept and is unaffected). When given, `_find_depressions` ANDs its result with `valid_mask`, so a depression can only be found in genuinely-surveyed terrain, never in extrapolated filler. `api/analyze_contour.py` (the KML/KMZ flow) passes its `valid_mask` through; `api/villages.py`/`api/recommend.py` (the live-DEM flow) are untouched.

**Rationale:** Tracks data provenance rather than applying a size-based heuristic. A connected-region-size cap was considered and rejected: it would risk breaking the legitimate large flat-bottomed-basin case `domain/catchment.py`'s own flood-fill tests rely on, and would be an unvalidated magic number. Provenance tracking means a genuinely large real depression (fully within surveyed data) is still correctly preferred, while a same-shaped interpolation artifact never is.

**Impact:** `kml_parser.py`'s `parse_contour_kml` return type changes from a 3-tuple to a 4-tuple — its one caller (`api/analyze_contour.py`) updated to match. `domain/catchment.py`'s `analyze_catchment`/`_find_depressions` both gain a backward-compatible optional parameter; every other existing caller (`api/villages.py`, `api/recommend.py`, and all of `test_catchment.py`'s existing tests) is unaffected by the new default. No schema or frontend changes.

---

## D-009: Address the catchment outlet by grid index, not by geographic coordinate

Date: 2026-09-01
Status: Accepted

**Context:** The KMZ/KML flow returned a completely degenerate pond recommendation for the project's real sample file — 0.0 m² surface area, 0.0 side length, 0.0 capture ratio at all three candidate depths. An initial hypothesis (interpolation artifacts, D-008) was implemented and then disproven by measurement. Instrumenting `_flood_fill_achievable_volume` step by step showed the flooded region containing the site was **empty at every iteration**, which is only possible if `catchment_mask[site]` is False: the selected pond site was not inside its own traced catchment. Confirmed directly — `catchment_mask[185, 143]` was False, with the nearest mask cell one step diagonally away, and the catchment's cell count (2711) disagreed with the flow accumulation at that same cell (2747), two numbers that are the same quantity by definition in D8 routing and must agree. Reproduced on synthetic terrain too (a radial basin, and the cone used by existing tests), so this was never KML-specific.

**Decision:** `analyze_catchment`'s `catchment_for` now calls `grid.catchment(x=candidate.col, y=candidate.row, xytype="index")` instead of converting the cell to lon/lat and passing `xytype="coordinate"`.

**Rationale:** pysheds' coordinate path snaps a supplied point to a cell **corner** (its `snap='corner'` default). We were handing it a cell **centre** (`affine * (col + 0.5, row + 0.5)`), which snaps to a neighbouring cell — so the returned catchment belonged to a different cell than the candidate, and frequently did not contain it. Everything anchored at the candidate afterwards then described a different place than the mask: the flood-fill's achievable volume (which returned zero whenever the site fell outside), the reported `pond_location`, and the reported `flow_accumulation_at_pond`. Addressing by index removes the lossy round-trip entirely rather than compensating for it — the trace starts exactly at the intended cell. (`snap='center'` would also have worked, but leaves the coordinate round-trip in place for no benefit.) Verified: the site now falls inside its own catchment on the real KML and on both synthetic terrains, and cell count equals flow accumulation exactly (2747 == 2747 on the real file; 546 == 546 on the click-map flow).

**Why it went unnoticed until now:** before D-007, pond dimensions were computed purely from runoff volume and never consulted the catchment mask at the site, so the inconsistency produced no visible symptom. D-007's terrain-driven sizing made the mask load-bearing, which turned a silent inconsistency into a visible zero.

**Impact:** One call in `domain/catchment.py`. Catchment areas shift slightly (the real KML: 25.8 ha → 26.2 ha; the click-map site: 46.8 ha → 48.7 ha) — these are corrections, not regressions. Two regression tests added, both asserting invariants that were genuinely violated: the pond site must lie inside its own catchment boundary, and a bowl-shaped basin must report non-zero achievable storage.

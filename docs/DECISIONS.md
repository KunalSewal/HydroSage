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
Status: Accepted

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

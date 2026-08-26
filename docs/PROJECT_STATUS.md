# HydroSage — Project Status & Handoff

Last updated: 2026-08-26 (end of the session that built the map UI and the Phase 1 catchment endpoint). Read this before doing anything else in a new session — it's the fastest way back to full context.

## Where the actual code lives right now — read this first

- **Main checkout:** `C:\Users\kunal\OneDrive\Desktop\CSD\HydroSage` (branch `main`) — has the original scaffold and the first backend slice (Hiware Bazar, OpenZenith-based elevation). It does **not** have the new map UI, the OpenTopography/Nominatim switch, or the catchment/KML work.
- **Worktree:** `C:\Users\kunal\OneDrive\Desktop\CSD\HydroSage\.claude\worktrees\village-map-selection` (branch `worktree-village-map-selection`) — has **everything** built in this session: the full frontend rebuild, the elevation/geocoding provider switch, and the Phase 1 catchment-analysis endpoint. This branch is **not yet merged into `main`**.

**To continue tomorrow: work in the worktree, not the main checkout,** until a decision is made to merge. If a fresh session starts in the main checkout, the new work won't be visible there.

## What this project actually is

A web app that recommends pond-construction sites for rural water conservation by analyzing terrain, catchment area, and rainfall (see `docs/PROJECT_BRIEF.md` for the original requirements, `docs/ARCHITECTURE.md` for design decisions, `docs/DECISIONS.md` for the full decision log — this file is a narrative summary layered on top of those, not a replacement).

Partway through this session, a second, more specific requirement surfaced: `docs/private/Phase1Req.txt` describes a separately-evaluated deliverable — a backend route that accepts an uploaded KML/KMZ contour map, identifies a suitable pond location, and estimates the catchment area, submitted with a report (GitHub link, working API URL, methodology writeup, demo, API docs). This is likely the actual graded piece, and it's a different input mode than the live-map flow (uploaded static contour data vs. a DEM fetched live from a click).

## What's built and verified

### Backend (`backend/app/`)

- **Village model + PostGIS migration** — from early in the session, unchanged since.
- **`ElevationClient`** (`infrastructure/elevation_client.py`) — originally built against OpenZenith; **switched to OpenTopography's Global DEM API** after OpenZenith had a full outage mid-session, then came back flaky (see D-005 in `DECISIONS.md`). Verified live.
- **`GeocodingClient`** (`infrastructure/geocoding_client.py`) — Nominatim, direct. Verified live (forward search + reverse).
- **Village find-or-create repository** (`infrastructure/village_repository.py`) — `find_nearby` (PostGIS `ST_DWithin` proximity dedup) / `create_village`.
- **`POST /villages`, `GET /villages/{id}/elevation`, `GET /geocode`** — all wired to real data, all tested against the real DB and real external APIs.
- **CORS middleware** — was completely missing until the final whole-branch review caught it. Without it, every single frontend→backend call was silently blocked in a real browser, despite every automated test and the build passing. Fixed and verified (`main.py`).
- **NEW — Phase 1 catchment analysis:**
  - `domain/catchment.py` — D8 flow-direction/accumulation via `pysheds`, picks a pond site (highest flow accumulation away from the raster edge), delineates the catchment, traces its boundary as a real polygon.
  - `infrastructure/kml_parser.py` — parses an uploaded contour KML's `<Placemark>` elevation lines, interpolates them (`scipy.interpolate.griddata`) into the same `(elevation array, BoundingBox)` shape `ElevationClient` produces, so **one catchment engine serves both input paths** (uploaded KML, or a live DEM fetch).
  - `POST /analyzeContour` — accepts a `.kml` upload, runs both, returns JSON (`pond_location`, `catchment_area_m2`/`hectares`, `catchment_boundary`, `source_bbox`).
  - **Verified end-to-end via real HTTP upload** of the actual sample `docs/private/contours_1m.kml` (159,113 contour points, ~4-5s to process) — real pond location, real traced boundary polygon (not a placeholder box), real catchment area.

### Frontend (`frontend/src/`)

- Full rebuild from the default Vite template: **Tailwind CSS v4 + Framer Motion + lucide-react + Vitest**.
- **Map-first UI:** `MapView` (Leaflet, Esri satellite basemap, click-to-select, bouncing marker via a custom `divIcon` + CSS animation, contour lines that reveal progressively rather than snapping in), `SearchBox` (place search via `/geocode`), `SitePanel` (staged status UI — `idle → locating → located → analyzing → analyzed | error` — with animated count-up elevation stats).
- **`useGeolocation`** (opens centered on the user, falls back to Bhilai/Durg, Chhattisgarh) and **`useSiteSelection`** (the state machine driving the whole flow, with a request-id guard against race conditions — see below) hooks.
- **User-confirmed working today** (2026-08-26): open the app → map loads → click a point → "Analyze this site" → contour lines draw onto the map → elevation range shows in the side panel. **This is the core loop and it works, live, in a real browser.**
- **Not wired up yet:** the Phase 1 catchment/KML feature has **zero frontend** — no upload control, no way to see a catchment boundary on the map. It's a backend-only JSON API right now, verified only via Swagger/curl.

## What went wrong and got fixed (worth knowing so it doesn't get re-broken)

1. **OpenZenith outage.** The originally-chosen elevation/geocoding provider had a full API outage mid-session, then came back flaky. Switched to OpenTopography + Nominatim directly. `docs/DECISIONS.md` D-005 has the full verification trail.
2. **A real SQLAlchemy test-isolation bug.** `tests/conftest.py`'s `db_session` fixture used a plain transaction/rollback pattern; `POST /villages`'s necessary `db.commit()` escaped it, meaning test data could leak permanently into the shared dev DB and silently corrupt later runs. Fixed with the standard SAVEPOINT pattern (`connection.begin_nested()` + an `after_transaction_end` listener).
3. **An async race condition in `useSiteSelection`.** Two quick map clicks (or a retry) could let a stale, slower-resolving response overwrite state a newer, faster call had already set. Fixed with a request-id guard shared across `selectPoint`/`analyze`; regression-tested by deliberately resolving calls out of order.
4. **The map never actually recentered.** `react-leaflet`'s `<MapContainer center={...}>` only uses `center` to instantiate the map on mount — not reactive. Geolocation resolving, or selecting a new site, never panned the camera. Fixed with a `RecenterOnChange` child component (`useMap()` + `flyTo`).
5. **CORS was completely missing** (see above) — the single most consequential bug, caught only because a final whole-branch review happened at all.
6. **Two stale/duplicate local servers caused real confusion today.** A Docker container (`hydrosage-api-1`) had been running for 25 hours on port 8000 — the frontend's default backend URL — serving code from *before* essentially all of today's backend work. Separately, a leftover Vite dev server (started by an implementer agent checking for boot errors, never cleaned up) was squatting on port 5173. Both were stopped; the current backend now runs cleanly on `:8000`, the current frontend on `:5173`. **If things look stale again, check `netstat`/`docker ps` for zombies before assuming the code is wrong.**
7. **`pysheds` 0.5 (latest release) calls `numpy.in1d`,** which recent `numpy` removed. Small compatibility shim added (`np.in1d = np.isin`) in `domain/catchment.py`.
8. **Catchment-boundary polygon tracing silently fell back to a crude 4-corner box, twice**, from two separate `pysheds` API misuses (a bare array passed where a `Raster` was required; then a `nodata` dtype mismatch between a float DEM viewfinder and an int mask). Both found by actually testing against the real sample KML rather than trusting the code — now traces a genuine several-hundred-point polygon.

## Open items — what's next

**From the final whole-branch review, not yet fixed:**
- No "locate me" button — the spec calls for one twice, it was never built (a plan gap, not caught until the final review).
- The marker/map don't move until the reverse-geocode round-trip finishes (a beat of nothing happening after a click). One-line fix: `App.tsx`'s `markerPosition` should derive from `state.lastPoint` (already exists, set synchronously) instead of `state.village` (only populated after the network call resolves).
- Failure responses render badly in the panel — `[object Object]` for a Pydantic validation error, a raw JSON-parse error message for a 500. `api/client.ts`'s `parseOrThrow` needs to handle non-string `detail` and non-JSON bodies.
- `useSiteSelection.analyze()` fires two API calls per click in dev (React `StrictMode` double-invokes the `setState` updater it's called from) — halves the effective OpenTopography daily quota during development. Fix: move the network call out of the `setState` updater.
- `docs/ARCHITECTURE.md` is stale — still describes the original OpenZenith-based pipeline, doesn't mention `/geocode`, `POST /villages`, or CORS.

**On the catchment methodology (discussed with the user, explicitly deferred):**
- Picking the single point with the *globally* highest flow accumulation tends to grab a very large share of the whole surveyed area as "the catchment" (on the sample KML: ~36% of the entire survey, ~179–311 hectares depending on grid resolution) — that's mathematically correct but not really "a farm pond's catchment." Worth a size constraint or a local-maxima approach later.
- The result is meaningfully sensitive to the interpolation grid resolution (179ha at 300×300 vs. 311ha at 200×200 on the same input) — worth understanding/stabilizing before this goes in a report as a methodology.

**Not started:**
- Any frontend for the catchment/KML feature — no upload control, no boundary-on-map visualization.
- Phase 1's actual deliverables: the report itself (GitHub link, working API URL, methodology writeup, demo), API documentation beyond the auto-generated Swagger.
- A decision on the worktree branch: keep building on it, or merge into `main`. The final review's verdict was "ready to merge, with fixes" — the fixes above are the "with fixes" part.

## How to resume

```
cd "C:\Users\kunal\OneDrive\Desktop\CSD\HydroSage\.claude\worktrees\village-map-selection"
```

Backend (from `backend/`, venv active):
```
DATABASE_URL=postgresql+psycopg://hydrosage:hydrosage@localhost:5432/hydrosage uvicorn app.main:app --port 8000 --reload
```

Frontend (from `frontend/`):
```
npm run dev
```
Opens on `:5173` by default — matches the CORS allowlist in `backend/app/main.py`. If port 5173 or 8000 is already occupied when you start these, check what's actually listening there first (`netstat -ano | grep <port>`, `docker ps`) rather than assuming it's already the right thing — see open item #6 above.

Docker: `postgis`, `redis`, `minio` should already be running (`docker compose ps`). The old `api`/`worker` containers were deliberately stopped (stale code) — don't restart them without rebuilding (`docker compose up -d --build api worker`) first, and be aware of the Docker Compose project-name/port-conflict risk documented in the SDD ledger (`.superpowers/sdd/2026-08-26-village-map-selection/progress.md`) if running from this worktree directory.

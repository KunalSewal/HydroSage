# HydroSage — Project Status & Handoff

Last updated: 2026-08-30, after the session that: prepared the app for deployment (Docker for the frontend, auto-migrations, configurable CORS, dropped the unused Celery worker), gave the KML-upload flow full parity with the click-map flow (rainfall/runoff/pond-sizing/land-availability), closed out the frontend polish backlog (locate-me button, marker lag, error messages, a real StrictMode double-fetch bug), and refreshed `ARCHITECTURE.md`. Read this before doing anything else in a new session.

## Where the code lives

- `main` and `worktree-village-map-selection` are **in sync** right now — every round of work this session was fast-forward-merged into `main` immediately after landing (`git push origin worktree-village-map-selection:main`), so there's no divergence to reconcile. Keep working in the worktree; merging stays a plain fast-forward as long as `main` isn't touched independently elsewhere.
- Git history was rewritten once this session (all commits on both branches, `git filter-branch`) to strip the `Co-Authored-By: Claude` trailer at the user's request, ahead of a presentation. New commits in this repo no longer add that trailer. If you're in a fresh session and someone asks "why does `git log` look rewritten," that's why — it was deliberate and force-pushed with explicit approval.
- The repo is **private**, solo-owned, 0 forks — that's why the history rewrite was low-risk. Don't assume that's still true without checking (`gh repo view --json isPrivate,forkCount`) if this ever becomes a team project.

## What this project is

A web app that recommends pond-construction sites for rural water conservation by analyzing terrain, catchment area, land availability, and rainfall (`docs/PROJECT_BRIEF.md` has the full requirements; `docs/ARCHITECTURE.md` is now current, see below; `docs/DECISIONS.md` is the decision log, through D-006). A separately-graded Phase 1 deliverable (`docs/private/Phase1Req.txt`, gitignored) asks specifically for a KML-upload → catchment-analysis API route with a report — this is likely the actual graded piece, and it now has full feature parity with the click-map flow (see below).

## What's built — the full pipeline, end to end

**Backend** (`backend/app/`), organized `api/` (routers) → `domain/` (pure logic) → `infrastructure/` (external I/O), per `ARCHITECTURE.md`'s module boundaries:

| Endpoint | Does |
|---|---|
| `POST /villages` | Find-or-create a village from a lat/lon click (PostGIS proximity dedup + Nominatim reverse geocode) |
| `GET /villages/{id}/elevation` | DEM (OpenTopography, MinIO-cached per village) → smoothed, elevation-colored contours → full catchment analysis (pond site + boundary + area) |
| `POST /villages/{id}/recommend` | Everything `/elevation` has, plus rainfall (Open-Meteo, 10yr) → runoff (coefficient method) → pond depth/size options (2/3/4m) → each checked against OSM-derived available land |
| `POST /analyzeContour` | Same catchment/contour engine, fed from an uploaded KML instead of a live DEM fetch, **plus the same rainfall/runoff/pond-sizing/land-availability recommendation `/recommend` has** — computed against the KML's own bbox centroid (no "village" row to key off) via the new shared `app/services/recommendation.py` |
| `GET /villages/{id}/rainfall` | Same rainfall data `/recommend` uses, standalone |
| `GET /geocode` | Nominatim place search |

Two caches, both this session, both because a specific real cost was identified and verified, not speculative:
- **DEM cache** (MinIO, `dem_cache.py`) — protects OpenTopography's 50-calls/day free tier. Verified: 14.7s cold fetch → 1.5s cached, byte-identical result.
- **Catchment-result cache** (Redis, `catchment_cache.py`) — avoids running the D8 pipeline twice when a user does "Analyze this site" then "Get pond recommendation" for the same site. Verified via direct Redis inspection that both endpoints share one computed result.

**The big correctness fix this session:** `domain/catchment.py`'s pond-siting used to pick the single point with the *globally* highest flow accumulation in the analyzed area — which is really "where does the biggest drainage line exit this map tile," not a farm pond's catchment. It consistently claimed 20–36% of whatever area was analyzed. Now it samples a spread of local accumulation maxima and picks the best-ranked one whose catchment area actually falls in a realistic range (1–50 hectares, grounded in Indian watershed-development literature). Real before/after: Bhilai/Durg catchment 813.8ha → 1.96ha; KML sample 178.76ha → 49.59ha. This is the single most important fix in the session — everything downstream (runoff volume, pond dimensions) was nonsensical before it and is realistic after.

**Frontend** (`frontend/src/`):
- Contours colored by elevation (hypsometric green→red ramp) instead of one flat color, on both the click-map and KML-upload flows, with a legend (`ContourLegend.tsx`) showing what the colors mean.
- Click-map flow: click → "Analyze this site" (contours + catchment, fast) → optional "Get pond recommendation" (rainfall/runoff/dimensions/land, slower) as a **second, explicit stage** — deliberately not bundled into one call, so browsing contours doesn't pay for rainfall+land lookups every time.
- KML-upload flow: everything in one call (contours + catchment + rainfall + runoff + pond sizing + land availability) — no second stage here, since `/analyzeContour` already returns it all at once and there's no "cheap first look vs. fuller analysis" distinction the way there is for browsing many different map clicks.
- `useSiteSelection` models the click-map recommendation as a sub-machine (`recommendationStatus`/`recommendation`/`recommendationError`) alongside the existing status machine, sharing its race-guard so a stale fetch from a superseded site can't clobber newer state.
- Locate-me button (`LocateButton.tsx`, top-right on the map) — `useGeolocation`'s `locate()` existed all along, just had no UI control before.
- Readable error messages throughout: `parseOrThrow` now handles both a Pydantic 422 validation error's array-shaped `detail` (was rendering as the literal text "[object Object]") and a non-JSON error body (was throwing a raw `JSON.parse` error). `SearchBox` now has a real searching/no-results/error state instead of silently doing nothing on failure.

**Two real bugs found and fixed this session, worth knowing about if similar ones show up elsewhere:**
- **React StrictMode double-fetch**, for real this time (was previously just a suspected/theoretical item). `useSiteSelection`'s `analyze()` and `getFullRecommendation()` both called their network request *from inside* the function passed to `setState()` — React StrictMode double-invokes exactly that kind of function in dev to catch impurities, so every OpenTopography/rainfall/land-availability call was silently firing twice while developing. Fixed by reading current state via a ref outside the updater instead, and there's now a real regression test for both (wraps `renderHook` in `<StrictMode>` and asserts the client mock was called exactly once) — the first tests in this codebase that actually exercise StrictMode's double-invoke behavior rather than just asserting final state.
- **No auto-migrations.** Found while testing the Docker deployment locally: a fresh Postgres volume under `docker compose up` had *no schema at all* until `alembic upgrade head` was run by hand. `backend/Dockerfile`'s `CMD` now runs it before starting `uvicorn`, every container start (safe on restarts — a no-op once applied).

**Verified live, real numbers, worth keeping as a reference for the report:**
- Bhilai/Durg: 1436mm/yr rainfall → 7,043 m³/yr runoff → pond options 42–59m square at 2–4m depth → 1155ha available land nearby, all fitting.
- KML sample: 49.6ha catchment, 1415mm/yr rainfall → 175,443 m³/yr runoff → pond options 209–296m square → 741.8ha available land nearby, all fitting.

## Deployment — prepared, not yet live

The app is now genuinely deployable (Docker Compose builds and runs the whole stack cleanly — verified locally end-to-end, including a fresh database), but **nothing is actually running on the target VM yet**. What's ready:
- `frontend/Dockerfile` (new — didn't exist before): multi-stage Node build → nginx serving the static output. `VITE_API_BASE_URL` is a build arg, baked in before the JS is built.
- `docker-compose.yml`: dropped the unused `worker` (Celery) service (see below), added the `frontend` service, `restart: unless-stopped` on everything, ports configurable via a new root-level `.env` (`API_PORT`, `FRONTEND_PORT`, `VITE_API_BASE_URL` — separate from `backend/.env`, which holds the app's actual secrets).
- CORS is now configurable (`CORS_ALLOWED_ORIGINS` setting) instead of hardcoded to `localhost:5173` — a deployed frontend's origin would otherwise have been silently rejected by the browser (this exact class of bug already broke the app once before, D-005).
- The user has SSH+sudo access to a VM with a public IP and (probably) Docker already available. Exact deployment checklist (clone, create both `.env` files, `docker compose up -d --build`, verify from both the VM and externally) was handed to the user to run themselves over SSH/tmux — not yet executed as of this writing. Ask the user for the outcome before assuming either way.

**The async job-queue question is resolved, not just documented as open.** `DECISIONS.md` D-001 kept Celery+Redis specifically for D8 catchment delineation; nothing ever actually dispatched a task to it. D-006 formally drops it: `app/api/catchment.py`, `app/api/jobs.py` (both pure `501` stubs for the abandoned design), and the `worker` Docker Compose service are all deleted. Redis stays, now justified by `catchment_cache.py` instead.

**`ARCHITECTURE.md` is current now, not stale** — rewritten to describe the actual module structure, including the new `app/services/` layer (see below), the two caches, and the dropped async job path. The historical HLD-summary/original-observations sections are kept as a record of the initial planning, clearly marked as historical.

**New module tier: `app/services/`.** `recommendation.py`'s `compute_recommendation_fields()` orchestrates rainfall → runoff → pond sizing → land availability, shared by both `/recommend` and `/analyzeContour` (extracted from what was previously duplicated-in-spirit logic sitting inside `/recommend`'s endpoint body). Not pure enough for `domain/` (real I/O — `RainfallClient`, `LandUseClient`), not an HTTP concern for `api/`. Documented properly in `ARCHITECTURE.md` now.

## What's NOT built

- **Phase 1's report deliverables** — GitHub link, methodology writeup, demo, API docs beyond auto-generated Swagger. Nothing written yet. This is probably the next real piece of work.
- **Actual deployment execution** — see "Deployment" above. The config is ready; running it on the VM is a to-do handed to the user.
- **Runoff: coefficient → real SCS Curve Number.** Still the fallback method — `land_availability.py`'s OSM data gives some land-cover signal now, but Curve Number also needs soil hydrologic group data this app doesn't have.
- **KML-flow's contour precision issue** (flagged early, never revisited): the KML's own precise ground-survey contour lines get thrown away and reinterpolated through a lossy 300×300 grid before being re-traced, purely for the sake of code reuse with the DEM path.

## Where to work next (real options, not a fixed order — ask the user)

1. **Deployment** — run the checklist on the VM (or troubleshoot it with the user, since I can't SSH in myself). Phase 1 is graded partly on a working API URL.
2. **Report writing** — the pipeline is complete and numbers are realistic now; the catchment-sizing fix methodology especially is worth writing up honestly.
3. **Runoff: coefficient → real SCS Curve Number**, if there's appetite for the extra rigor.
4. **KML-flow's contour precision issue** (above) — a real fix, just never prioritized over functional gaps.

## Known environment quirks (don't waste time rediscovering these)

- **Host vs. Docker hostnames:** `.env` uses Docker-network hostnames (`postgis`, `minio`, `redis`) for the containerized `api`/`worker` services. Running the backend directly on the host (as this session did throughout, via `uvicorn` outside Docker) needs `DATABASE_URL`, `OBJECT_STORAGE_ENDPOINT`, and `REDIS_URL` overridden to `localhost` equivalents — see the exact command below.
- **`overpass-api.de` is unreachable from this dev sandbox specifically** (connection timeout, not a DNS or code issue — confirmed general internet access works fine otherwise). `overpass.openstreetmap.fr` works as a substitute for local testing (`OVERPASS_BASE_URL=https://overpass.openstreetmap.fr`). The shipped default stays `overpass-api.de` per the documented architecture — this is very likely a quirk of this specific sandbox's network egress, not something to "fix" in the app itself. The app already degrades gracefully (returns `null` availability) if Overpass is unreachable in any environment, so this isn't a functional risk either way.
- **Overpass mirrors reject a generic User-Agent** (403) — `land_use_client.py` already sends a descriptive one; if you swap providers/mirrors again, check this first if you get an unexplained 403.
- **`git filter-branch` runs from PowerShell need absolute paths** for `--msg-filter` scripts — a relative path silently fails to resolve depending on what working directory the internal `sh -c` invocation uses.

## How to resume

```
cd "C:\Users\kunal\OneDrive\Desktop\CSD\HydroSage\.claude\worktrees\village-map-selection"
```

Backend (from `backend/`, venv active):
```
DATABASE_URL=postgresql+psycopg://hydrosage:hydrosage@localhost:5432/hydrosage OBJECT_STORAGE_ENDPOINT=localhost:9000 REDIS_URL=redis://localhost:6379/0 uvicorn app.main:app --port 8000 --reload
```

Frontend (from `frontend/`):
```
npm run dev
```
Opens on `:5173`, matches the CORS allowlist in `backend/app/main.py`.

Docker: `postgis`, `redis`, `minio` should already be running (`docker compose ps`; if not, `docker compose up -d postgis redis minio` — Docker Desktop itself needs to be running first on Windows).

**Alternative: run the whole stack in Docker instead of on the host.** `docker compose up -d --build` now brings up everything, including `api` and `frontend` (nginx-served static build on `:8080` by default, backend on `:8000`) — this is the exact same config that'll run on the deployment VM, verified working locally. Needs a root-level `.env` (`cp .env.example .env`) and `backend/.env` (`cp backend/.env.example backend/.env`, then fill in a real `OPENTOPOGRAPHY_API_KEY` and set `CORS_ALLOWED_ORIGINS` to include whichever port you set `FRONTEND_PORT` to). Migrations run automatically on container start now — no manual `alembic upgrade head` step needed either way.

Tests: `pytest -q` (backend), `npx vitest run` (frontend). Integration tests hitting live external APIs are gated behind `RUN_INTEGRATION_TESTS=1` and skipped by default — run them explicitly (with the host-vs-Docker env overrides above) before trusting a change to any external client.

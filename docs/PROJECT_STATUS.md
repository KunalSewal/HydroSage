# HydroSage — Project Status & Handoff

Last updated: 2026-08-29, after the session that finished the terrain-analysis pipeline (rainfall → runoff → pond sizing → land availability), fixed a major catchment-sizing bug, and wired the results into the frontend. Read this before doing anything else in a new session.

## Where the code lives

- `main` and `worktree-village-map-selection` are **in sync** right now — every round of work this session was fast-forward-merged into `main` immediately after landing (`git push origin worktree-village-map-selection:main`), so there's no divergence to reconcile. Keep working in the worktree; merging stays a plain fast-forward as long as `main` isn't touched independently elsewhere.
- Git history was rewritten once this session (all commits on both branches, `git filter-branch`) to strip the `Co-Authored-By: Claude` trailer at the user's request, ahead of a presentation. New commits in this repo no longer add that trailer. If you're in a fresh session and someone asks "why does `git log` look rewritten," that's why — it was deliberate and force-pushed with explicit approval.
- The repo is **private**, solo-owned, 0 forks — that's why the history rewrite was low-risk. Don't assume that's still true without checking (`gh repo view --json isPrivate,forkCount`) if this ever becomes a team project.

## What this project is

A web app that recommends pond-construction sites for rural water conservation by analyzing terrain, catchment area, land availability, and rainfall (`docs/PROJECT_BRIEF.md` has the full requirements; `docs/ARCHITECTURE.md` is currently **stale**, see Open Items; `docs/DECISIONS.md` is the decision log). A separately-graded Phase 1 deliverable (`docs/private/Phase1Req.txt`, gitignored) asks specifically for a KML-upload → catchment-analysis API route with a report — this is likely the actual graded piece.

## What's built — the full pipeline, end to end

**Backend** (`backend/app/`), organized `api/` (routers) → `domain/` (pure logic) → `infrastructure/` (external I/O), per `ARCHITECTURE.md`'s module boundaries:

| Endpoint | Does |
|---|---|
| `POST /villages` | Find-or-create a village from a lat/lon click (PostGIS proximity dedup + Nominatim reverse geocode) |
| `GET /villages/{id}/elevation` | DEM (OpenTopography, MinIO-cached per village) → smoothed, elevation-colored contours → full catchment analysis (pond site + boundary + area) |
| `POST /villages/{id}/recommend` | Everything `/elevation` has, plus rainfall (Open-Meteo, 10yr) → runoff (coefficient method) → pond depth/size options (2/3/4m) → each checked against OSM-derived available land |
| `POST /analyzeContour` | Same catchment/contour engine, fed from an uploaded KML instead of a live DEM fetch — no rainfall/land/recommend integration (see Not Built) |
| `GET /villages/{id}/rainfall` | Same rainfall data `/recommend` uses, standalone |
| `GET /geocode` | Nominatim place search |

Two caches, both this session, both because a specific real cost was identified and verified, not speculative:
- **DEM cache** (MinIO, `dem_cache.py`) — protects OpenTopography's 50-calls/day free tier. Verified: 14.7s cold fetch → 1.5s cached, byte-identical result.
- **Catchment-result cache** (Redis, `catchment_cache.py`) — avoids running the D8 pipeline twice when a user does "Analyze this site" then "Get pond recommendation" for the same site. Verified via direct Redis inspection that both endpoints share one computed result.

**The big correctness fix this session:** `domain/catchment.py`'s pond-siting used to pick the single point with the *globally* highest flow accumulation in the analyzed area — which is really "where does the biggest drainage line exit this map tile," not a farm pond's catchment. It consistently claimed 20–36% of whatever area was analyzed. Now it samples a spread of local accumulation maxima and picks the best-ranked one whose catchment area actually falls in a realistic range (1–50 hectares, grounded in Indian watershed-development literature). Real before/after: Bhilai/Durg catchment 813.8ha → 1.96ha; KML sample 178.76ha → 49.59ha. This is the single most important fix in the session — everything downstream (runoff volume, pond dimensions) was nonsensical before it and is realistic after.

**Frontend** (`frontend/src/`):
- Contours colored by elevation (hypsometric green→red ramp) instead of one flat color, on both the click-map and KML-upload flows, with a legend (`ContourLegend.tsx`) showing what the colors mean.
- Click-map flow: click → "Analyze this site" (contours + catchment, fast) → optional "Get pond recommendation" (rainfall/runoff/dimensions/land, slower) as a **second, explicit stage** — deliberately not bundled into one call, so browsing contours doesn't pay for rainfall+land lookups every time.
- `useSiteSelection` models the recommendation as a sub-machine (`recommendationStatus`/`recommendation`/`recommendationError`) alongside the existing status machine, sharing its race-guard so a stale fetch from a superseded site can't clobber newer state.
- KML-upload flow: contours + catchment boundary + pond marker + legend, but no pond-dimension recommendation (see Not Built).

**Verified live, real numbers, worth keeping as a reference for the report:**
- Bhilai/Durg: 1436mm/yr rainfall → 7,043 m³/yr runoff → pond options 42–59m square at 2–4m depth → 1155ha available land nearby, all fitting.
- KML sample: 49.59ha catchment, 281-point traced boundary.

## What's NOT built

- **KML-upload flow has no rainfall/runoff/pond-dimension recommendation.** It has no "village" row to hang a rainfall/land lookup off — doing this means calling `RainfallClient`/`LandUseClient` directly against the KML's own centroid coordinates, real backend work, not frontend wiring.
- **Nothing is deployed anywhere.** Phase 1 explicitly requires a working, publicly-reachable API URL. This literally has not been started.
- **Phase 1's report deliverables** — GitHub link, methodology writeup, demo, API docs beyond auto-generated Swagger.
- **The async job-queue question is unresolved.** `DECISIONS.md` D-001 explicitly decided to keep Celery+Redis specifically because D8 catchment delineation is CPU-heavy — but everything built this session runs synchronously inline, and it's been fine at this scale (the slowest observed request was ~22s, only when Overpass was degrading). Either build the job queue for real, or write a new decision entry formally superseding D-001's "keep Celery" call with what actually got built and why it's held up fine.
- **`ARCHITECTURE.md` is badly stale** — still describes an async job pipeline that was never built this way, and predates rainfall, `/recommend`, land-use, and both caches entirely. Needs a real pass, not a patch.

**Carried over from earlier sessions, still open (lower priority, real but minor):**
- No "locate me" button on the map.
- `App.tsx`'s `markerPosition` derives from `state.village` (post-network) instead of `state.lastPoint` (synchronous) — causes a beat of lag after a click. One-line fix, never applied.
- `api/client.ts`'s `parseOrThrow` doesn't handle non-string Pydantic `detail` or non-JSON error bodies — ugly error text in edge cases.
- `useSiteSelection` double-fetches under React StrictMode in dev (harmless in prod; now largely mitigated by DEM caching anyway).
- `SearchBox` has no error handling for a failed place search.

## Where to work next (real options, not a fixed order — ask the user)

1. **Deployment** — arguably the highest-leverage next step: Phase 1 is graded partly on a working API URL, and nothing is live.
2. **KML-flow recommendation parity** — give the upload flow the same rainfall/runoff/pond-sizing/land-check the click-map flow has.
3. **Report writing** — much easier now that the pipeline is complete and numbers are realistic; the methodology (esp. the catchment-sizing fix) is genuinely worth writing up honestly.
4. **`ARCHITECTURE.md` refresh + the job-queue decision** — affects "system design" grading, not urgent functionally.
5. **Frontend polish backlog** (above).
6. **Runoff: coefficient → real SCS Curve Number.** More feasible now that `land_availability.py` exists (some land-cover signal), though CN also needs soil hydrologic group data this app still doesn't have.
7. **KML-flow's contour precision issue** (flagged early, never revisited): the KML's own precise ground-survey contour lines get thrown away and reinterpolated through a lossy 300×300 grid before being re-traced, purely for the sake of code reuse with the DEM path. Fixable without much complexity, just never prioritized.

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

Docker: `postgis`, `redis`, `minio` should already be running (`docker compose ps`; if not, `docker compose up -d postgis redis minio` — Docker Desktop itself needs to be running first on Windows). The `api`/`worker` containers are deliberately not used this session (everything ran on the host instead) — don't assume they're up to date if you start them.

Tests: `pytest -q` (backend), `npx vitest run` (frontend). Integration tests hitting live external APIs are gated behind `RUN_INTEGRATION_TESTS=1` and skipped by default — run them explicitly (with the host-vs-Docker env overrides above) before trusting a change to any external client.

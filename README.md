# HydroSage

**AI-Powered Geospatial Intelligence for Sustainable Water Planning**

A web application that recommends suitable pond-construction sites for rural water conservation, by analyzing terrain elevation, catchment area, rainfall, and land availability. Built for village administrators who currently have to make these siting decisions without access to the underlying terrain and rainfall data.

## Phase 1 submission

**[docs/PHASE1_REPORT.md](docs/PHASE1_REPORT.md)** — the submission report: catchment
estimation approach, demonstration on the provided sample map, and full API documentation.

The graded endpoint is `POST /analyzeContour`, which takes a KML/KMZ contour map as
`contour_map` (multipart form data) and returns the sited pond and its delineated
catchment as JSON:

```bash
curl -X POST http://10.1.75.53:3265/analyzeContour \
  -F "contour_map=@contours_1m.kml"
```

## Documentation

- [docs/PHASE1_REPORT.md](docs/PHASE1_REPORT.md) — Phase 1 submission report
- [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md) — product requirements
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — architecture and design rationale
- [docs/DECISIONS.md](docs/DECISIONS.md) — decision log

## Stack

- **Backend:** Python 3.12, FastAPI, Celery + Redis (async catchment/runoff jobs), PostgreSQL + PostGIS (spatial data), MinIO (S3-compatible object storage for DEM tiles and rasters)
- **Frontend:** React + TypeScript + Vite, react-leaflet (interactive map), Chart.js (rainfall/runoff visualizations)
- **Geospatial processing:** rasterio, pysheds (D8 flow accumulation / catchment delineation), scikit-image (contour generation)

See `docs/ARCHITECTURE.md` for the full rationale behind these choices.

## Layout

- `backend/` — FastAPI service, Celery worker, domain logic (terrain, catchment, runoff, pond sizing)
- `frontend/` — React + TypeScript + Vite client
- `docker-compose.yml` — API, worker, Redis, PostGIS, MinIO for local development

## Quickstart

Full stack:
```
docker compose up --build
```
API docs (auto-generated): http://localhost:8000/docs

Backend only (from `backend/`, with a virtualenv activated):
```
pip install -e ".[dev]"
uvicorn app.main:app --reload
pytest
```

Frontend only (from `frontend/`):
```
npm install
npm run dev
```

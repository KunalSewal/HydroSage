# Project Brief

Source of product requirements, extracted from the project description. This document is authoritative for product intent unless a decision in `DECISIONS.md` explicitly revises it.

## Source documents

| Document | Provided | Notes |
|---|---|---|
| Project description | [docs/private/ProjectDescription.txt](private/ProjectDescription.txt) | Authoritative source of product requirements |
| Handwritten HLD | [docs/private/HLD.txt](private/HLD.txt) | Initial architecture proposal, not a commitment — see `ARCHITECTURE.md` |

## Problem statement

Rural water scarcity is worsened by unplanned or poorly sited pond construction: wasted excavation effort, inadequate catchment, or ponds that dry up. Village administrators pick sites manually, without access to the terrain, catchment, and rainfall data needed to make an informed decision. HydroSage is a web application that analyzes terrain elevation, catchment areas, land availability, and rainfall patterns to recommend suitable locations, depth, and storage capacity for pond construction.

## Users / actors

- **Village administrator** (primary and only user role named in the brief) — selects a village and a candidate site, reviews the recommendation.
- No multi-tenant or auth requirement is stated in the project description. The HLD assumes an API-gateway auth layer; that's not asked for by the brief (see open question #4 and `ARCHITECTURE.md`).

## Core use cases (functional requirements, verbatim intent)

1. Display satellite imagery for a selected village.
2. Visualize contour maps derived from elevation data.
3. Identify available land suitable for pond excavation.
4. Estimate the catchment area contributing runoff to a selected location.
5. Query historical rainfall data via public APIs.
6. Estimate runoff volume from rainfall + catchment area.
7. Recommend an appropriate pond depth and approximate storage capacity.
8. Overlay all of the above — location, catchment, rainfall stats, runoff, pond dimensions, maps — into one view.

## Scope

### In scope

- Terrain/elevation analysis (contours) for a selected village.
- Catchment delineation and runoff estimation.
- Historical rainfall lookup via public API(s).
- Pond depth/capacity recommendation, checked against available land.
- Interactive map overlay combining all results.
- Deliverables: complete source code, installation guide, API documentation, an accessible frontend, final technical report.

### Out of scope (unless later revised)

- Land-record ownership/legal verification — no reliable live government land-record API exists (acknowledged in the HLD); a proxy dataset stands in for it.
- Multi-region or production-scale deployment — the brief describes one evaluated web app, not a scaled service.
- User authentication / multi-tenancy — not requested by the brief.

## Constraints

- Suggested (explicitly not mandatory) stack: Python, Flask or FastAPI, OpenCV, MongoDB/PostgreSQL, elevation APIs, rainfall APIs (IMD, Open-Meteo, NASA POWER, etc.), a basic frontend library.
- This is a graded deliverable against a fixed rubric (below), which implies a bounded, demo-able scope rather than an open-ended production system.

## Evaluation weighting (from the brief — read as a priority signal, not just a grading formality)

| Criterion | Marks |
|---|---|
| System functionality | 35 |
| Terrain and catchment analysis | 20 |
| Frontend and visualization | 5 |
| Software design and code quality | 15 |
| System design and management | 15 |
| Documentation and report | 10 |
| **Total** | **100** |

Functionality plus terrain/catchment analysis correctness (55/100) outweigh frontend polish and infrastructure sophistication combined (20/100). Effort should be sequenced accordingly: get the geospatial analysis right and working end-to-end before investing in infrastructure elaborateness. See `ARCHITECTURE.md` for how this reframes the HLD's proposed system design.

## Resolved

1. ~~Elevation API~~ — OpenZenith confirmed as a real, working API by the user. See `DECISIONS.md` D-002.
2. ~~Solo/team, deadline~~ — exploratory, no hard deadline; the goal is an industrial-quality build, not a minimum-viable submission. See `DECISIONS.md` D-001.

## Open questions

1. No reliable government land-record API exists (acknowledged by the HLD's own risk list). Need a concrete proxy dataset/approach for "available government land." Current lean: OpenStreetMap land-use polygons — see `ARCHITECTURE.md` open questions.
2. Satellite imagery source is undecided — the HLD lists Bhuvan or Sentinel-based sources "depending on availability." Current lean: a public tile basemap (Esri World Imagery / Sentinel-2 cloudless) — see `ARCHITECTURE.md` open questions.
3. What defines a "village" boundary, and how is the list of selectable villages sourced (a fixed demo set vs. a real administrative boundary dataset)? Not specified in the brief. Current lean: a small curated demo set to start — see `ARCHITECTURE.md` open questions.

# Map-first village selection and contour visualization

Date: 2026-08-26
Status: Approved (design), pending implementation

## Context

The backend (`docs/ARCHITECTURE.md`) already has a working, verified pipeline: given a village's bounding box, it fetches real DEM tiles from OpenZenith and returns contour geometry (`GET /villages/{id}/elevation`). But the only way to exercise it is Swagger UI or raw `curl` — there is no visual product yet. The frontend is still the default Vite template.

This spec covers the first real frontend build: a map the user can actually use to pick a site and see its terrain, replacing the earlier plan of a pre-seeded village list (Maharashtra-only, then a proposed Chhattisgarh district dataset) with a click-anywhere flow that needs no curated dataset at all. This directly implements functional requirements #1 (imagery), #2 (contours), and part of #8 (overlay view) from `docs/PROJECT_BRIEF.md`, and supersedes the "leaning toward a curated village list" note in `docs/ARCHITECTURE.md` open question #3.

## Goals

- A user can open the app, see a real interactive map, and select any point on it — not just points from a pre-loaded list.
- Selecting a point shows that point's terrain contours, generated for the selected area only (never a whole-map or whole-region contour layer).
- Every pipeline stage (locating, reverse-geocoding, fetching elevation, generating contours) is visible to the user as it happens — no single opaque "loading" spinner covering multiple seconds of backend work.
- The map opens centered on the user's real location when permitted, so it's immediately relevant rather than a blank world map.

## Non-goals (this pass)

Catchment delineation UI, rainfall chart, pond depth/dimension recommendation, and the land-availability overlay are not built in this pass. Each is a real backend capability that doesn't exist yet (see `docs/ARCHITECTURE.md` open questions and the API design's remaining `501` stubs) and gets its own pass, following the same staged-panel pattern established here once its backend piece is ready.

## User flow

1. App loads. Browser requests geolocation permission. If granted, map centers on the user's location; if denied or unavailable, it falls back to a fixed default center near Bhilai/Durg, Chhattisgarh (~21.19°N, 81.30°E, zoom 11). A "locate me" control lets the user retry at any time.
2. The user either types a place name into a search box (geocoded via the backend, which proxies OpenZenith's `/api/geocode`) to jump the map there, or clicks directly anywhere on the map.
3. On click, a marker drops immediately (instant feedback) and a side panel opens showing a "locating..." state while the backend reverse-geocodes the point for a human-readable label.
4. Once the site is identified, the panel offers "Analyze this site." Triggering it walks through visible stages in the panel: "fetching elevation..." → contour lines draw onto the map as they arrive → elevation stats (min/max) populate the panel. A satellite imagery basemap layer is available as a toggle throughout (Sentinel-2 tiles via the existing OpenZenith proxy path).
5. If any stage fails (network error, geolocation denied, reverse-geocode miss, elevation fetch failure), the panel shows a specific inline error for that stage — not a silent failure or a generic toast — with a retry action where it makes sense.

## Architecture

**Frontend** (`frontend/src`): React + TypeScript + Vite, react-leaflet for the map (already installed). New structure:
- `components/MapView.tsx` — the Leaflet map, click handler, marker, satellite tile layer, contour polyline layer.
- `components/SearchBox.tsx` — geocode search, recenters `MapView` on a result.
- `components/SitePanel.tsx` — the side panel; owns the staged state machine for the selected site (`idle → locating → located → analyzing → analyzed | error`).
- `hooks/useGeolocation.ts` — wraps the browser Geolocation API with the permission/fallback logic from the user flow.
- `api/client.ts` — thin fetch wrapper for the backend endpoints used below; one function per endpoint, typed responses matching the backend's Pydantic schemas.

**Backend** — one small additive endpoint, everything else already exists and is unchanged:
- `POST /villages` — body `{lat, lon}`, each validated to a real coordinate range (`lat` -90..90, `lon` -180..180; FastAPI/Pydantic rejects anything outside that with a 422 before it reaches the handler). Reverse-geocodes the point (new thin `geocoding_client.py` in `app/infrastructure/`, same pattern as `elevation_client.py`), builds a bounding box around it the same way `scripts/seed_villages.py` does today, and creates a `Village` row — or returns the existing one if a village's centroid already exists within 500m of the clicked point (`ST_DWithin` on `centroid::geography`), avoiding duplicate rows every time someone clicks near the same spot. Returns the same `VillageOut` shape `GET /villages` already returns.
- `GET /villages/{id}/elevation` — unchanged, already returns contour geometry scoped to that village's bounding box.

## Data flow

```
click (lat, lon)
  → POST /villages {lat, lon}
      → reverse-geocode (OpenZenith) for the label
      → find-or-create Village row (PostGIS ST_DWithin proximity check)
      ← VillageOut {id, name, state, district, lat, lon}
  → GET /villages/{id}/elevation
      → DEM tiles (OpenZenith) → mosaic → contour extraction (existing, unchanged)
      ← ElevationOut {bbox, min/max elevation, contours[]}
  → MapView draws contours; SitePanel shows stats
```

## Error handling

- Geolocation denied/unavailable: fall back to the fixed default center; no error shown (this is an expected, non-broken path), just the "locate me" control staying available.
- Reverse-geocode or elevation fetch fails (OpenZenith unreachable, timeout, bad response): `SitePanel` shows an inline error for that specific stage with a "retry" button; the map marker stays so the user doesn't lose their selection.
- `POST /villages` with `lat`/`lon` outside valid coordinate range: Pydantic validation returns 422 automatically. A geographically valid but unresolvable point (e.g. open ocean, no reverse-geocode match): reverse-geocode call returns no result, handler responds 422 with a distinct message; panel surfaces it as "couldn't identify a site here."

## Visual design & animation

The user asked explicitly for a premium look, not a functional-but-generic dashboard — this adds real dependencies, not just CSS tweaks:

- **Styling:** Tailwind CSS (utility-first — faster to get a distinctive, custom look than fighting a component library's default appearance). Replaces the current bare `App.css`/`index.css` from the Vite template.
- **Animation:** Framer Motion, for the staged reveals the flow already calls for — panel slide-in, marker drop with a bounce, elevation stats counting up rather than snapping in, and (the centerpiece) contour lines drawing themselves onto the map stroke-by-stroke as they arrive, rather than appearing all at once. This is where "every step visually displayed" (the user's words from the design discussion) becomes something that actually feels considered rather than just functional.
- **Icons:** `lucide-react` — consistent, modern icon set instead of mixed/default glyphs.
- **Typography:** a deliberate font pairing via Google Fonts, loaded once in `index.html` — a clean geometric sans for UI text and a slightly more distinctive display face for headings/stats, rather than the browser default.
- **Basemap:** a clean, muted basemap tile layer (e.g. CARTO Positron) for the default/unselected map state, switching to the OpenZenith Sentinel-2 imagery layer once a site is selected — makes the "before" and "after" states visually distinct rather than the map looking the same throughout.
- **Motion principles:** shared easing/duration tokens (not ad hoc per-component timings) so the whole app feels like one system; every async stage from the staged-feedback design gets a matching motion treatment, not just a text label change.

This doesn't change the component boundaries or data flow already described above — it changes what those components are built with and how their state transitions look.

## Testing

- Backend: unit test for the find-or-create proximity logic against a real PostGIS (following the existing pattern — real DB via Docker Compose, not mocked); an `integration`-marked test (skipped by default, same convention as `test_elevation_client.py`) exercising the real reverse-geocode call.
- Frontend: component tests for `SitePanel`'s state machine (idle/locating/analyzing/error transitions) using mocked API responses; `useGeolocation` tested with a mocked `navigator.geolocation`. End-to-end manual verification against the running Docker Compose stack, same as the backend slice was verified — clicking a real point and confirming real contours render.

## Open items carried forward (not blocking this pass)

Everything in `docs/ARCHITECTURE.md`'s open questions besides village selection (land-availability proxy) is unaffected by this spec.

# Catchment, pond-volume, and KML-fidelity improvements — design spec

Date: 2026-09-01
Status: Approved by user across 3 clarifying questions; ready for implementation planning.

## Context

While explaining the current pipeline (`docs/Explanation.md`), the user asked me to review a sibling reference project, [`virtualvasu/contour-detection-service`](https://github.com/virtualvasu/contour-detection-service) — a smaller, KML/KMZ-only submission that appears to target the same Phase 1 brief (same sample file, `contours_1m.kml`). I read both codebases in full and found three concrete gaps worth closing, plus one open question about how a fourth difference (pond-siting philosophy) should be reconciled — this spec covers all four, now resolved.

The user's explicit priority, stated directly: **implement whichever approach is more physically/hydrologically correct, not whichever is easiest to build.**

## What's changing, and why

### 1. Site selection: prefer real depressions, don't replace accumulation ranking

**Current behavior** (`domain/catchment.py`): candidates are sampled from the D8 flow-accumulation grid (after `pysheds`' `fill_pits`/`fill_depressions`/`resolve_flats` conditioning), ranked by accumulation, and the highest-ranked one whose traced catchment area falls in a realistic 1–50ha band is picked.

**The gap:** a high-accumulation point is a good site for a *check dam across a drainage channel* (water flows through it), but not necessarily where water would *naturally pool* — that's a real topographic depression (a local low point). The reference repo's site-selection criterion is exactly the latter: rank real depressions by contributing catchment size. Both are physically legitimate pond types; neither model alone is complete.

**Decision:** add depression detection as a **preference layer on top of** the existing accumulation-based candidate search, not a replacement for it — confirmed with the user across two questions (site model, then flow scope):
- Depression detection must run on the **raw, unconditioned** elevation grid. `pysheds`' conditioning steps exist specifically to eliminate sinks so flow-accumulation has no dead ends — by the time accumulation is computed, real depressions are already gone from that grid. A cell is a depression if none of its 8 neighbors on the *original* array are strictly lower.
- Each detected depression's "score" is read from the *already-computed* conditioned accumulation grid at that same location (how much land drains toward that natural bowl), not recomputed from scratch — this reuses existing computation rather than building a second flow model, and naturally suppresses interpolation-noise sinks (a spurious single-cell dip has near-zero accumulation and won't compete with genuine candidates) without needing the reference repo's separate fixed cell-count filter.
- When selecting among candidates whose catchment area falls in the realistic 1–50ha range, a depression-flagged candidate wins over a non-depression one; if none of the in-range candidates are depressions, current behavior (highest accumulation) is unchanged. The existing closest-fallback logic (when *nothing* fits the range) is unchanged.
- Applies to **both flows** (click-map live DEM and KML upload) — both produce the same `(elevation grid, bbox)` shape by the time this code runs, so there's no flow-specific reason to treat them differently.

### 2. Pond volume: report terrain-grounded holding capacity alongside the runoff-driven target

**Current behavior** (`domain/pond.py`): pond size is entirely demand-driven — target storage = one year's estimated runoff (`domain/runoff.py`), then surface area is back-solved at three fixed candidate depths (2/3/4m), assuming a flat square footprint. Nothing checks whether the actual ground at the chosen site could physically hold that shape.

**The gap:** the reference repo computes pond volume the opposite way — supply-driven: flood-fill the actual depression at the chosen site, step by step, tracking flooded area at each elevation increment, and integrate area-vs-elevation into a real achievable volume, capped at a realistic max depth. This is grounded in the real terrain shape; ours currently isn't.

**Decision:** keep the runoff-driven target as the primary recommendation (confirmed with the user: it's the only thing that answers "how big does this pond need to be for this catchment's rainfall"), and add the terrain's actual holding capacity as a **check**, following the same pattern `fits_available_land` already establishes:
- For the site `analyze_catchment` already selected, flood-fill upward from its base elevation using the grid's own resolution, tracking flooded area at each step, stopping at whichever comes first: the flood spilling past the traced catchment's own boundary (or the raster's edge), or reaching the deepest candidate depth (4m — no need for a separately-tuned cap; it's already bounded by the existing candidate-depth range in `domain/pond.py`). Integrate area vs. elevation (trapezoidal) into an achievable volume at each of the three candidate depths.
- Each `PondOption`'s existing `fits_available_land` field gets a sibling: `fits_terrain_capacity: bool | None` — `true` if the terrain's achievable volume at that depth meets or exceeds the runoff-driven target, `false` if not, `null` if the check couldn't be computed (e.g. degenerate flat terrain with no meaningful local relief) — same "absence of an answer, not a false negative" convention `fits_available_land` already uses.
- Applies to **both flows**, per the same reasoning as §1.

### 3. KMZ support

**The gap:** `infrastructure/kml_parser.py` and the `POST /analyzeContour` endpoint only accept `.kml`. The reference repo unzips a `.kmz` (detecting the zip signature) and reads whichever entry is `doc.kml`, or the first `.kml` file found otherwise.

**Decision:** adopt the same approach. The endpoint accepts both `.kml` and `.kmz` by extension; the parser transparently unzips before parsing if the upload is a zip archive.

### 4. KML contour display precision

**The gap:** for the KML-upload flow, `kml_parser.py` currently keeps only the raw `(lon, lat, elevation)` points from parsing, interpolates them onto a 300×300 grid, and `domain/terrain.py` **re-traces brand-new contour lines from that grid** via marching squares — the same code path used for a live DEM. This throws away the KML's own precise, ground-surveyed line geometry (already flagged as a known gap in `docs/PROJECT_STATUS.md`).

**Decision:** for the KML/KMZ flow only, return the originally-parsed line geometry (lightly simplified for payload size, the way the reference repo does) as the response's `contours` field, instead of calling `generate_contours()`. The interpolated grid is still computed and still used for everything else (catchment delineation, elevation stats, the new terrain-capacity check) — only the *displayed* line geometry changes. The live-DEM click flow is untouched: a DEM is already a raster with no "original vector lines" to fall back to, so it keeps using `generate_contours()`'s marching-squares tracing exactly as today.

## What's explicitly out of scope

- **Not** replacing `pysheds` with a hand-rolled D8 implementation, and **not** switching to true UTM reprojection for cell-size/area math (the reference repo does both; the accuracy difference at the scales this app operates at is judged negligible, and pysheds' conditioning pipeline is still needed for accumulation ranking regardless).
- **Not** touching the runoff-coefficient method, rainfall aggregation, or land-availability logic — unaffected by any of the above.
- **Not** building frontend UI to display `fits_terrain_capacity` or any precision differences in contour rendering. The API response gains the new field / the more precise KML line geometry; a symmetrical frontend display update (mirroring how `fits_available_land` is already shown) is a natural next step, not required by this spec. Flag if you want it bundled in.

## What's reused unchanged

- `domain/runoff.py`, `domain/rainfall.py`, `domain/land_availability.py`, every `infrastructure/*_client.py`, both caches, the whole frontend, the DB schema, and `domain/terrain.py`'s marching-squares tracing (still used for the live-DEM flow).
- `domain/catchment.py`'s existing candidate-sampling and area-band-targeting logic — extended, not replaced.
- `domain/pond.py`'s existing depth/footprint math — extended with a new check, not replaced.

## Testing approach

- New unit tests for depression detection (`domain/catchment.py`) against small synthetic elevation grids with a known, deliberately-placed bowl shape — same style as the existing `test_catchment.py`.
- New unit tests for the flood-fill/achievable-volume function against a synthetic grid with a known analytically-computable volume at a given depth.
- New unit tests for KMZ unzipping (`test_kml_parser`-equivalent) using a small in-memory zip built in the test itself, plus a malformed-zip-that-looks-like-a-zip case.
- New unit test confirming the KML flow's `contours` response field matches the parsed line geometry (simplified) rather than a re-traced grid.
- Live verification (this project's established pattern) against the real sample KML (`docs/private/contours_1m.kml`) and a real click-map site, confirming: a plausible depression-preferring site gets picked where one exists nearby, `fits_terrain_capacity` reports sensible values, KMZ upload works end-to-end, and the KML flow's displayed contour lines visibly match the source file's precision.

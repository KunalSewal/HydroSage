# Terrain-driven pond sizing — design spec

Date: 2026-09-01
Status: Approved by user across 2 clarifying questions; ready for implementation planning.

## Context

While testing the app after the depression-preferred site-selection and terrain-capacity-check work landed (previous plan, `docs/superpowers/specs/2026-09-01-catchment-pond-improvements-design.md`), the user reported unrealistic pond dimensions in the live UI: a 213.7m × 213.7m pond at 2m depth (~91,000 m³) for a 25.8ha catchment, and similarly a 289.9m square pond for the Bhilai/Durg site's 46.8ha catchment.

Diagnosis (confirmed with real numbers from the live app, not assumed): the catchment areas themselves (25.8ha, 46.8ha) are within this project's own documented "realistic farm/community pond catchment" range (1–50ha, `domain/catchment.py`). The problem is downstream of site selection, in how the pond gets *sized*: `domain/pond.py`'s `recommend_pond_dimensions` targets a storage volume equal to **100% of one full year's estimated catchment runoff**, then back-solves a footprint. At a 25–47ha catchment, "capture everything" is inherently a reservoir-scale target, not a farm-pond-scale one — the demand-driven design goal itself is the unrealistic part, not the catchment or the site.

This demand-driven formula predates this session's site-selection work; it was previously masked because the old (pre-depression-preference) site selection happened to land on a smaller catchment (1.96ha) for the same test site, which kept the runoff-capture target small by coincidence. Depression-preference correctly found a better-fitted site near the top of the realistic-area band, which is what newly exposed the sizing formula never having been validated there.

A sibling reference project (`virtualvasu/contour-detection-service`, already reviewed in the previous plan's work) avoids this entirely with a **supply-driven** model: pond volume is bounded by how much the actual terrain can physically hold (flood-fill, capped at a realistic max depth), never by an arbitrary capture-everything target. HydroSage already computes exactly this data — `domain/catchment.py`'s `analyze_catchment()` produces `achievable_volume_m3_by_depth: dict[float, float]` via flood-fill at the already-selected site (built in the previous plan) — but currently only uses it as a secondary boolean check (`fits_terrain_capacity`) alongside the still-primary demand-driven size, never to actually size anything.

## Decision

Switch pond sizing from demand-driven to **pure supply-driven**: each candidate depth's pond volume becomes that depth's own real terrain-holding capacity (`achievable_volume_m3_by_depth[depth]`), not a shared runoff-capture target. Confirmed with the user across two questions:
1. **Pure supply-driven, not a hybrid min(demand, supply).** A hybrid still inherits the demand formula's questionable "100% capture" assumption as a ceiling in the small-catchment case; pure supply-driven matches the reference repo's model exactly and directly fixes the reservoir-scale numbers.
2. **Single site only** — site selection (which point becomes "the" pond site) is unchanged. Expanding to multiple candidate sites (the reference repo's top-3, which the user separately liked) is explicitly deferred to a future piece of work that will naturally pair with frontend changes (multiple map markers, a reveal-more interaction) already deferred until after this fix.

## What's changing

### 1. New sizing function, old one untouched

`domain/pond.py` gains `size_pond_from_terrain_capacity(achievable_volume_m3_by_depth: dict[float, float]) -> list[PondOption]`, reusing the existing `PondOption` dataclass shape (`depth_m`, `surface_area_m2`, `side_length_m`) — each option's footprint is back-solved from that depth's own achievable volume: `surface_area_m2 = volume / depth`, `side_length_m = sqrt(surface_area_m2)`, same formula `recommend_pond_dimensions` already uses, just fed an independent volume per depth instead of one shared target.

`recommend_pond_dimensions` and `PondRecommendation` are **not modified** — they remain a valid, independently-tested "given a target volume, back-solve footprints" utility, just no longer the app's primary sizing path. No existing test in `test_pond.py` needs to change.

### 2. `services/recommendation.py` calls the new function

`compute_recommendation_fields`'s signature is **unchanged** (`lat, lon, bbox, catchment_area_m2, achievable_volume_m3_by_depth`) — it already receives everything the new sizing needs. Internally, it calls `size_pond_from_terrain_capacity(achievable_volume_m3_by_depth)` instead of `recommend_pond_dimensions(target_storage_m3=runoff.runoff_volume_m3)`.

Because the signature doesn't change, **neither `api/recommend.py` nor `api/analyze_contour.py` needs any changes** — both already pass `achievable_volume_m3_by_depth` through from the previous plan's work.

### 3. `PondOptionOut` field changes (`schemas/recommend.py`)

- **Removed:** `fits_terrain_capacity`. Its question ("does the demand-sized pond fit the terrain") stops applying once the pond *is* sized to terrain capacity by construction — checking terrain capacity against itself is vacuous. Safe to remove: the frontend never rendered this field (explicitly deferred in the previous plan), so nothing downstream breaks.
- **Added:** `annual_runoff_capture_fraction: float | None` per option — `achievable_volume_m3_by_depth[depth] / runoff_volume_m3` (guarded against division by zero, `None` if runoff volume is zero). Replaces the removed pass/fail framing with an honest, continuous stat: how much of a typical year's catchment runoff this depth's terrain-sized pond actually captures. Follows the same nullable convention as `fits_available_land`.
- **Unchanged:** `depth_m`, `surface_area_m2`, `side_length_m`, `fits_available_land` (still a valid, orthogonal check regardless of how the footprint was derived), and the top-level `average_annual_rainfall_mm`/`runoff_volume_m3`/`runoff_coefficient` fields (still legitimate informative context — a catchment's annual runoff is a real, useful number even though it no longer drives pond size).

### 4. Documentation

Add a `docs/DECISIONS.md` entry recording this correction — what was wrong (demand-driven sizing produced reservoir-scale dimensions once site-selection started landing on realistically-large catchments), what replaced it (supply-driven, terrain-capacity sizing), and why — matching this project's established practice of logging every methodology change for the eventual written report.

## What's explicitly out of scope

- Site selection itself (`_find_depressions`, `_select_pond_site`'s ranking/preference logic) — unchanged.
- Multiple candidate sites (top-3, reveal-more UX) — deferred to a future piece of work paired with the frontend changes already deferred.
- Any frontend changes — the API response shape changes (field removed, field added); displaying the new field is a future step, same deferral as the previous plan.
- `domain/runoff.py`'s coefficient method itself — unchanged; still used to compute the informative annual-runoff figure.
- The flat-plateau depression false-positive finding parked during the previous plan's final review — unrelated to sizing, not reopened here.

## Testing approach

- New unit tests for `size_pond_from_terrain_capacity` in `test_pond.py`: different volumes at different depths produce independently-correct, differing footprints (unlike the old shared-target model, where all depths scaled off one number) — verifies the function doesn't silently fall back to treating the dict as a single shared value.
- `recommend_pond_dimensions`'s existing test suite requires no changes — confirms the deliberate non-modification.
- Live verification against the real sample KMZ and the click-map flow (same sites already used in the previous plan's verification), confirming the pond dimensions now look plausible for the same catchment areas that previously produced reservoir-scale numbers.

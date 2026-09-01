# Farm-pond-scale siting and dual-bound sizing — design spec

Date: 2026-09-01
Status: Approved by user; ready for implementation planning.

## Context

After D-009 fixed the site/catchment consistency bug, the KML flow's numbers became honestly computed but still read as implausible for a farm pond. Measured on the real sample KMZ: a 26.17 ha catchment producing 141.3m / 177.2m / 250.0m square ponds at 2/3/4m depth.

Investigation showed the numbers are not wrong — they are the correct answer to the wrong question. Two findings drove this design:

1. **Bounding by runoff alone barely helps.** `min(terrain, runoff)` on that site gives 141m / 176m / 152m — only the 4m option improves. A 26 ha catchment genuinely delivers ~92,500 m³/yr, and a pond capturing a meaningful share of that is inherently large.

2. **The catchment band spans two different interventions.** Indian watershed practice separates a *farm pond* (a dug excavation, serving a few hectares) from a *check dam / percolation tank* (a bund across a drainage line, serving tens of hectares). `MIN/MAX_CATCHMENT_AREA_M2` is currently 1–50 ha, which covers both. At 26 ha the analysis faithfully returns a check-dam-scale structure, which is then labelled a "pond."

Three physical bounds on pond size exist. The app currently applies one:

| Bound | Question it answers | Applied before this change |
|---|---|---|
| Terrain capacity | What can this landform hold? | Yes (D-007) |
| Annual runoff | What does the catchment deliver? | No — reported only |
| Practical excavation | What would anyone actually dig? | No |

## Decision

Target farm-pond scale at site selection, and bound volume by both physical limits. A practical-excavation cap is deliberately **not** introduced: it would be an arbitrary constant doing the real work, and a clamped number stops being physically derived.

### 1. Narrow the target catchment band

`domain/catchment.py`: `MAX_CATCHMENT_AREA_M2` changes from `500_000` (50 ha) to `50_000` (5 ha). `MIN_CATCHMENT_AREA_M2` stays at `10_000` (1 ha).

The band becomes 1–5 ha — farm-pond scale under Indian watershed-development practice, rather than a range spanning farm ponds and check dams. The constant's docstring is updated to state that the app deliberately targets the farm-pond end and no longer recommends check-dam-scale structures.

**Verified there is no fallback risk on either input path** (a band with no in-range candidate would silently fall through to `_select_pond_site`'s closest-fit fallback):

| Band | Real sample KML: in-range candidates (depressions) | Live DEM (Bhilai/Durg): in-range candidates (depressions) |
|---|---|---|
| 1–50 ha (current) | 144 (36) | 365 (77) |
| 1–5 ha (this change) | 86 (22) | 172 (27) |

### 2. Bound pond volume by terrain *and* runoff

`domain/pond.py`'s primary sizing function currently takes only `achievable_volume_m3_by_depth` (terrain capacity per depth, from the flood-fill). It gains the catchment's annual runoff volume, and each depth's storage becomes:

```
volume(depth) = min(terrain_capacity(depth), annual_runoff_m3)
```

then footprint is back-solved as before (`surface_area_m2 = volume / depth`, `side_length_m = sqrt(surface_area_m2)`).

Both bounds are real measured quantities: one from the flood-fill over actual terrain, one from rainfall × catchment area × runoff coefficient. Neither is a tuned constant.

The function is renamed from `size_pond_from_terrain_capacity` to `size_pond_options`, since it is no longer terrain-only, with signature:

```python
size_pond_options(
    achievable_volume_m3_by_depth: dict[float, float],
    annual_runoff_m3: float,
) -> list[PondOption]
```

`services/recommendation.py` passes the runoff volume it already computes.

### 3. `runoff_capture_ratio` becomes bounded, and stays informative

With the runoff bound applied, `runoff_capture_ratio` is now ≤ 1.0 by construction. It remains useful because it identifies which bound is binding:

- **exactly 1.00** — runoff-limited: the terrain could hold more, but the catchment does not deliver more water
- **below 1.00** — terrain-limited: the water is available, but the landform cannot hold it

Because that distinction is already encoded in the value, **no separate `limited_by` field is added**. Only the field's doc comment in `schemas/recommend.py` changes; the response shape does not.

### Measured effect on the real sample KMZ

Selected site becomes a 4.35 ha catchment delivering 15,401 m³/yr:

| Depth | Before | After | Binding bound |
|---|---|---|---|
| 2m | 141.3m square | 62.9m square | terrain (captures 51%) |
| 3m | 177.2m square | 71.6m square | runoff (captures 100%) |
| 4m | 250.0m square | 62.1m square | runoff (captures 100%) |

The small end stays coherent: at the 1 ha band floor with this rainfall, capturing a full year's runoff needs roughly a 34m square — consistent with MGNREGA farm-pond dimensions.

## What's explicitly out of scope

- **No practical-excavation cap.** Rejected above; both applied bounds stay physically derived.
- **No `limited_by` response field.** Redundant with `runoff_capture_ratio`.
- **No change to site-selection mechanics** — `_find_depressions`, `_select_pond_site`'s depression preference and memoisation, and the D-009 index-based outlet addressing are all untouched. Only the area band they filter against changes.
- **No change to the runoff coefficient method** (`domain/runoff.py`) or to `recommend_pond_dimensions`, the retained demand-driven utility from D-007.
- **No frontend changes.** The response shape is unchanged; the deferred UI work (logo/zoom overlap, bottom-sheet sizing, map refocus) remains deferred.

## Accepted consequence

The tool stops recommending check-dam and percolation-tank scale structures. For a catchment larger than 5 ha, site selection will now prefer a smaller sub-catchment within the analysed area rather than the whole drainage. This is the intent — the tool models farm ponds — but it is a genuine narrowing of what the app will suggest, and should be stated as such in the written report.

## Testing approach

- Unit tests for the dual-bound sizing function: terrain-limited case (terrain < runoff) uses terrain volume; runoff-limited case (runoff < terrain) uses runoff volume; each depth is bounded independently.
- A test asserting `runoff_capture_ratio` never exceeds 1.0, which is the invariant the runoff bound introduces.
- Existing `domain/catchment.py` tests continue to assert the selected catchment falls within `MIN/MAX_CATCHMENT_AREA_M2`; they read the constants rather than hard-coded values, so they follow the narrowed band automatically — this must be confirmed, not assumed.
- Live verification against the real sample KMZ and the click-map flow, confirming both produce farm-pond-scale dimensions and that neither falls through to the closest-fit fallback.

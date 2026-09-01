# Farm-Pond-Scale Siting and Dual-Bound Sizing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make pond recommendations farm-pond scale by targeting 1–5 ha catchments at site selection and bounding pond volume by both physical limits — what the terrain can hold *and* what the catchment delivers.

**Architecture:** Two independent changes. `domain/pond.py`'s sizing function gains the annual runoff volume and takes `min(terrain capacity, annual runoff)` per depth; `domain/catchment.py`'s `MAX_CATCHMENT_AREA_M2` drops from 50 ha to 5 ha so site selection looks for farm-pond-scale catchments in the first place. No new tuned constants are introduced — both bounds are measured quantities.

**Tech Stack:** Python 3.12, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-01-farm-pond-scale-sizing-design.md`

## Global Constraints

- **No practical-excavation cap.** Both applied bounds must stay physically derived (terrain flood-fill, and rainfall × area × coefficient). Do not add a clamp constant.
- **No `limited_by` response field.** `runoff_capture_ratio` already encodes which bound binds (exactly 1.0 = runoff-limited, below 1.0 = terrain-limited).
- **No change to site-selection mechanics** — `_find_depressions`, `_select_pond_site`, and D-009's index-based outlet addressing are untouched. Only the area band they filter against changes.
- **No change to `domain/runoff.py`** or to `recommend_pond_dimensions` (the retained demand-driven utility from D-007).
- **No frontend changes.** The API response shape does not change; only a doc comment on an existing field changes.
- **`MIN_CATCHMENT_AREA_M2` stays at `10_000`.** Only `MAX_CATCHMENT_AREA_M2` changes.

---

### Task 1: Bound pond volume by terrain *and* runoff

**Files:**
- Modify: `backend/app/domain/pond.py`
- Modify: `backend/app/services/recommendation.py`
- Modify: `backend/app/schemas/recommend.py`
- Modify: `backend/tests/test_pond.py`

**Interfaces:**
- Consumes: the existing `PondOption` dataclass (`depth_m`, `surface_area_m2`, `side_length_m`), unchanged.
- Produces: `size_pond_options(achievable_volume_m3_by_depth: dict[float, float], annual_runoff_m3: float) -> list[PondOption]`, replacing `size_pond_from_terrain_capacity`. Task 4's live verification depends on this being wired through `services/recommendation.py`.

This task combines the rename and its only call site deliberately: the rename breaks `services/recommendation.py`'s import, so splitting them would leave a non-importable intermediate commit that no reviewer could sensibly approve on its own.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_pond.py`. Extend the existing import line at the top of the file to:

```python
from app.domain.pond import CANDIDATE_DEPTHS_M, recommend_pond_dimensions, size_pond_options
```

Then replace the three existing `size_pond_from_terrain_capacity` tests (they test the old single-bound signature and are superseded) with these:

```python
def test_size_pond_options_uses_terrain_capacity_when_it_is_the_smaller_bound():
    # Terrain holds less than the catchment delivers -> terrain binds.
    options = size_pond_options({2.0: 4000.0, 3.0: 9000.0}, annual_runoff_m3=1_000_000.0)
    by_depth = {o.depth_m: o for o in options}

    assert by_depth[2.0].surface_area_m2 == pytest.approx(2000.0)
    assert by_depth[3.0].surface_area_m2 == pytest.approx(3000.0)


def test_size_pond_options_uses_annual_runoff_when_it_is_the_smaller_bound():
    # The catchment delivers less than the terrain could hold -> runoff binds,
    # and a pond bigger than the water available to fill it is wasted digging.
    options = size_pond_options({2.0: 400_000.0, 4.0: 800_000.0}, annual_runoff_m3=10_000.0)
    by_depth = {o.depth_m: o for o in options}

    assert by_depth[2.0].surface_area_m2 == pytest.approx(5000.0)   # 10_000 / 2
    assert by_depth[4.0].surface_area_m2 == pytest.approx(2500.0)   # 10_000 / 4


def test_size_pond_options_applies_the_bound_independently_at_each_depth():
    # Terrain binds at 2m, runoff binds at 4m, within one call.
    options = size_pond_options({2.0: 6000.0, 4.0: 900_000.0}, annual_runoff_m3=40_000.0)
    by_depth = {o.depth_m: o for o in options}

    assert by_depth[2.0].surface_area_m2 == pytest.approx(3000.0)    # terrain: 6000 / 2
    assert by_depth[4.0].surface_area_m2 == pytest.approx(10_000.0)  # runoff: 40_000 / 4


def test_size_pond_options_never_sizes_beyond_the_annual_runoff():
    # The invariant the runoff bound introduces: stored volume can never
    # exceed a year's runoff, so runoff_capture_ratio can never exceed 1.0.
    runoff = 25_000.0
    options = size_pond_options({2.0: 1e9, 3.0: 1e9, 4.0: 1e9}, annual_runoff_m3=runoff)

    for option in options:
        assert option.surface_area_m2 * option.depth_m <= runoff + 1e-6


def test_size_pond_options_returns_options_sorted_by_depth():
    options = size_pond_options({4.0: 8000.0, 2.0: 4000.0, 3.0: 6000.0}, annual_runoff_m3=1e9)
    assert [o.depth_m for o in options] == [2.0, 3.0, 4.0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `backend/`): `pytest tests/test_pond.py -k size_pond_options -v`
Expected: FAIL — `ImportError: cannot import name 'size_pond_options'`

- [ ] **Step 3: Implement the dual-bound sizing function**

In `backend/app/domain/pond.py`, replace the whole `size_pond_from_terrain_capacity` function (it currently starts at `def size_pond_from_terrain_capacity(` and ends with the closing `]` of its return) with:

```python
def size_pond_options(
    achievable_volume_m3_by_depth: dict[float, float],
    annual_runoff_m3: float,
) -> list[PondOption]:
    """Back-solves a flat square footprint at each candidate depth from the
    smaller of two real physical bounds:

    * what the terrain can hold at that depth (domain/catchment.py's
      flood-fill over the actual landform), and
    * what the catchment actually delivers in a year (domain/runoff.py).

    Sizing to terrain alone overshoots whenever the basin is larger than
    the water available to fill it -- a pond that would only ever be part
    full is wasted excavation. Sizing to runoff alone overshoots whenever
    the landform cannot hold that much. The binding bound is whichever is
    smaller, and it varies by depth (see docs/DECISIONS.md D-010).

    This is the app's primary pond-sizing entry point (see
    services/recommendation.py); recommend_pond_dimensions remains
    available for a target-volume use case, but is no longer how the
    app's own recommendation is sized.

    Note: surface_area_m2 describes a flat-bottomed square footprint sized to
    hold this depth's bounded volume (the excavation you'd dig), not the
    flood-fill's own traced inundation shape at that depth -- an irregular
    basin's actual water surface at a given depth is generally larger than
    volume/depth would suggest for a flat-bottomed prism.
    """
    return [
        PondOption(
            depth_m=depth,
            surface_area_m2=(area := min(terrain_capacity_m3, annual_runoff_m3) / depth),
            side_length_m=area**0.5,
        )
        for depth, terrain_capacity_m3 in sorted(achievable_volume_m3_by_depth.items())
    ]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_pond.py -v`
Expected: PASS — every test in the file, including all pre-existing `recommend_pond_dimensions` tests (untouched).

- [ ] **Step 5: Wire it through the service**

In `backend/app/services/recommendation.py`, change the import:

```python
from app.domain.pond import size_pond_from_terrain_capacity
```

to:

```python
from app.domain.pond import size_pond_options
```

Replace the call:

```python
    pond_options = size_pond_from_terrain_capacity(achievable_volume_m3_by_depth)
```

with:

```python
    pond_options = size_pond_options(achievable_volume_m3_by_depth, runoff.runoff_volume_m3)
```

Then replace the `runoff_capture_ratio` computation:

```python
                runoff_capture_ratio=(
                    achievable_volume_m3_by_depth[o.depth_m] / runoff.runoff_volume_m3
                    if runoff.runoff_volume_m3 > 0
                    else None
                ),
```

with:

```python
                # Derived from the option's own bounded volume, not the raw
                # terrain capacity -- otherwise this would still report the
                # unbounded ratio the sizing no longer uses.
                runoff_capture_ratio=(
                    (o.surface_area_m2 * o.depth_m) / runoff.runoff_volume_m3
                    if runoff.runoff_volume_m3 > 0
                    else None
                ),
```

- [ ] **Step 6: Update the schema's doc comment**

In `backend/app/schemas/recommend.py`, replace:

```python
    # This depth's terrain capacity as a multiple of a typical year's
    # catchment runoff (e.g. 0.15 = 15% of a year's runoff; a value
    # above 1.0 means the terrain could hold more than a year's runoff).
    # Unbounded, not a 0-1 fraction. None only when runoff_volume_m3 is
    # exactly 0, to avoid dividing by zero.
    runoff_capture_ratio: float | None
```

with:

```python
    # What share of a typical year's catchment runoff this depth's pond
    # holds. Bounded to at most 1.0, since the pond is never sized beyond
    # the runoff available to fill it. Exactly 1.0 means runoff-limited
    # (the terrain could hold more, but the catchment doesn't deliver
    # more); below 1.0 means terrain-limited. None only when
    # runoff_volume_m3 is exactly 0, to avoid dividing by zero.
    runoff_capture_ratio: float | None
```

- [ ] **Step 7: Confirm no stale references remain and the suite passes**

Run: `grep -rn "size_pond_from_terrain_capacity" backend/`
Expected: no matches.

Run: `pytest -q`
Expected: PASS — all tests.

- [ ] **Step 8: Commit**

```bash
git add backend/app/domain/pond.py backend/app/services/recommendation.py backend/app/schemas/recommend.py backend/tests/test_pond.py
git commit -m "Bound pond volume by both terrain capacity and annual runoff"
```

---

### Task 2: Narrow the target catchment band to farm-pond scale

**Files:**
- Modify: `backend/app/domain/catchment.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `MAX_CATCHMENT_AREA_M2 == 50_000`. Task 4's live verification depends on this.

**Why this task adds no new test:** the behavioural assertion already exists. `backend/tests/test_catchment.py`'s `test_analyze_catchment_returns_a_realistically_sized_pond_catchment` asserts `MIN_CATCHMENT_AREA_M2 <= result.catchment_area_m2 <= MAX_CATCHMENT_AREA_M2` by importing the constants, so it follows the narrowed band automatically and is a real check of it. A test asserting the constant equals 50_000 would only restate the source line. This was verified against all three synthetic terrains the test suite uses before writing this plan — under a 1–5 ha band the uniform slope yields 175 in-range candidates (selection returns 4.76 ha), the cone 409 (returns 4.57 ha), and the radial basin 237 (returns 4.96 ha, with non-zero achievable volumes 3457/6884/11316 m³). No test falls through to the closest-fit fallback.

- [ ] **Step 1: Narrow the band and update its rationale**

In `backend/app/domain/catchment.py`, replace:

```python
# A realistic catchment scale for a small farm/community pond under Indian
# watershed-development practice -- most farm ponds serve a few hectares;
# larger community ponds/check dams might serve a few tens of hectares.
# Not the single "correct" number (no such thing without a real, sited
# survey), but a documented, literature-grounded range that keeps the
# recommendation plausible instead of claiming a third of the map tile.
MIN_CATCHMENT_AREA_M2 = 10_000  # 1 hectare
MAX_CATCHMENT_AREA_M2 = 500_000  # 50 hectares
```

with:

```python
# The catchment scale this app deliberately targets: a farm pond under
# Indian watershed-development practice, which serves a few hectares.
#
# This band used to run to 50 hectares, which spans two different
# interventions -- a farm pond (a dug excavation) and a check dam or
# percolation tank (a bund across a drainage line, serving tens of
# hectares). At the top of that range the analysis correctly returned a
# check-dam-scale structure, which then read as an absurd "pond": a
# 26 ha catchment produced a 250m-square recommendation. Narrowing the
# band makes site selection look for sites at the scale this app
# actually models. The trade-off is accepted and real: the app no longer
# recommends check-dam or percolation-tank scale structures at all.
# See docs/DECISIONS.md D-010.
MIN_CATCHMENT_AREA_M2 = 10_000  # 1 hectare
MAX_CATCHMENT_AREA_M2 = 50_000  # 5 hectares
```

- [ ] **Step 2: Run the full suite**

Run (from `backend/`): `pytest -q`
Expected: PASS — all tests, including `test_analyze_catchment_returns_a_realistically_sized_pond_catchment`, which now asserts against the narrowed band, and the two D-009 regression tests (pond site inside its own catchment; basin reports non-zero storage).

- [ ] **Step 3: Commit**

```bash
git add backend/app/domain/catchment.py
git commit -m "Target farm-pond-scale catchments: narrow the band from 50ha to 5ha"
```

---

### Task 3: Record the decision in `docs/DECISIONS.md`

**Files:**
- Modify: `docs/DECISIONS.md`

**Interfaces:** none — documentation only.

- [ ] **Step 1: Append the new entry**

The file currently ends with D-009's "Impact" paragraph. Append a separator and this entry:

```markdown

---

## D-010: Target farm-pond scale, and bound pond volume by terrain *and* runoff

Date: 2026-09-01
Status: Accepted

**Context:** With D-009's site/catchment consistency bug fixed, the numbers became honestly computed but still implausible as a farm pond: the real sample KMZ produced 141m / 177m / 250m square ponds at 2/3/4m depth for a 26.17 ha catchment. Two measurements reframed the problem. First, bounding by runoff alone barely helps — `min(terrain, runoff)` on that site gives 141m / 176m / 152m, improving only the 4m option, because a 26 ha catchment genuinely delivers ~92,500 m³/yr. Second, `MIN/MAX_CATCHMENT_AREA_M2` was 1–50 ha, a range spanning two interventions that Indian watershed practice treats separately: a farm pond (a dug excavation serving a few hectares) and a check dam or percolation tank (a bund across a drainage line serving tens of hectares). At 26 ha the analysis was faithfully returning a check-dam-scale structure and calling it a pond.

**Decision:** Two changes. `MAX_CATCHMENT_AREA_M2` drops from 500,000 (50 ha) to 50,000 (5 ha), so site selection targets farm-pond scale; `MIN_CATCHMENT_AREA_M2` stays at 10,000 (1 ha). And `domain/pond.py`'s primary sizing function, renamed from `size_pond_from_terrain_capacity` to `size_pond_options`, now takes the annual runoff volume and sizes each depth to `min(terrain capacity, annual runoff)` rather than terrain alone.

**Rationale:** Both bounds are measured physical quantities — one from the flood-fill over the actual landform, one from rainfall × catchment area × runoff coefficient. A practical-excavation cap was considered and rejected: it would be an arbitrary constant doing the real work, and a clamped number stops being physically derived, which cuts against this project's standing priority of physical correctness over convenience. Fixing the scale at site selection addresses the cause rather than clamping the symptom. Verified before committing that neither input path loses its candidate pool under the narrower band: the real sample KML has 86 in-range candidates (22 of them depressions), the live DEM at Bhilai/Durg has 172 (27 depressions), and all three synthetic terrains in the test suite stay in range.

**Impact:** On the real sample KMZ, the selected site becomes a 4.35 ha catchment delivering 15,401 m³/yr, and the recommendations become 62.9m / 71.6m / 62.1m squares (terrain-limited at 2m capturing 51%; runoff-limited at 3m and 4m capturing 100%). `runoff_capture_ratio` is now bounded to at most 1.0 by construction and identifies the binding bound: exactly 1.0 is runoff-limited, below 1.0 is terrain-limited — so no separate field was added for that. The API response shape is unchanged. **Accepted consequence:** the app no longer recommends check-dam or percolation-tank scale structures; for a catchment larger than 5 ha it will prefer a smaller sub-catchment within the analysed area. This should be stated in the written report.
```

- [ ] **Step 2: Commit**

```bash
git add docs/DECISIONS.md
git commit -m "Record D-010: farm-pond-scale targeting and dual-bound sizing"
```

---

### Task 4: Live verification

**Files:** none (verification only)

**Interfaces:** none — exercises the whole change end to end.

- [ ] **Step 1: Rebuild and restart the backend**

```bash
docker compose build api
docker compose up -d api
```

Wait for `curl -s http://localhost:8000/health` to return `{"status":"ok"}`. (A transient Docker Hub `failed to fetch oauth token` error has occurred intermittently in this environment; retry the build once if it appears.)

- [ ] **Step 2: Verify the KMZ upload flow**

Zip the sample KML into a KMZ if one isn't already present, then:

```bash
curl -s -X POST http://localhost:8000/analyzeContour -F "file=@<path-to-sample.kmz>" -o /tmp/kmz.json -w "HTTP %{http_code}\n"
python -c "
import json
d = json.load(open('/tmp/kmz.json'))
print('catchment ha:', round(d['catchment_area_hectares'], 2))
print('cells:', d['catchment_cell_count'], 'accumulation:', d['flow_accumulation_at_pond'])
print('runoff m3/yr:', round(d['runoff_volume_m3']))
for o in d['pond_options']:
    print(' ', o['depth_m'], 'm ->', round(o['side_length_m'], 1), 'm square, capture', round(o['runoff_capture_ratio'], 3))
"
```

Expected: HTTP 200. Catchment between 1 and 5 ha. Side lengths in the tens of metres, not hundreds (the spec's measured expectation is roughly 63m / 72m / 62m). Every `runoff_capture_ratio` ≤ 1.0. `catchment_cell_count` equals `flow_accumulation_at_pond` (the D-009 invariant must still hold).

- [ ] **Step 3: Verify the click-map flow**

```bash
curl -s -X POST http://localhost:8000/villages -H "Content-Type: application/json" -d '{"lat": 21.19, "lon": 81.3}' -o /tmp/v.json -w "HTTP %{http_code}\n"
python -c "import json; print(json.load(open('/tmp/v.json'))['id'])"
```

Take the printed id, then:

```bash
curl -s -X POST "http://localhost:8000/villages/<id>/recommend" -o /tmp/rec.json -w "HTTP %{http_code}\n"
python -c "
import json
d = json.load(open('/tmp/rec.json'))
print('runoff m3/yr:', round(d['runoff_volume_m3']))
for o in d['pond_options']:
    print(' ', o['depth_m'], 'm ->', round(o['side_length_m'], 1), 'm square, capture', round(o['runoff_capture_ratio'], 3))
"
```

Expected: HTTP 200, farm-pond-scale side lengths, every `runoff_capture_ratio` ≤ 1.0.

Note: the click-map flow caches its `CatchmentResult` in Redis for an hour (`infrastructure/catchment_cache.py`), so a site analysed before this change may return the pre-change catchment. If the returned catchment exceeds 5 ha, flush that key (or use a different lat/lon) and re-run rather than recording a stale result as a failure.

- [ ] **Step 4: Confirm no new server errors**

```bash
docker logs village-map-selection-api-1 --since 5m | grep -iE "error|exception|traceback" | grep -v "Overpass\|overpass"
```

Expected: no output beyond the known Overpass-unreachable degradation ("land-availability lookup failed"), which is a pre-existing environment quirk in this sandbox and returns 200 regardless.

- [ ] **Step 5: Run the full suite one final time**

```bash
cd backend && DATABASE_URL=postgresql+psycopg://hydrosage:hydrosage@localhost:5432/hydrosage OBJECT_STORAGE_ENDPOINT=localhost:9000 REDIS_URL=redis://localhost:6379/0 python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 6: Report**

Summarise the before/after dimensions for both flows, and state explicitly whether each depth came out terrain-limited or runoff-limited.

# Terrain-Driven Pond Sizing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix unrealistic, reservoir-scale pond dimensions by switching pond sizing from demand-driven (target = 100% of a year's catchment runoff) to supply-driven (target = the site's own real terrain-holding capacity at each depth, already computed via flood-fill).

**Architecture:** A new pure function in `domain/pond.py` sizes ponds from per-depth achievable-volume data instead of one shared runoff target; the existing demand-driven function is kept, unmodified, as a separate utility. `services/recommendation.py` switches which one it calls — its own public signature doesn't change, so neither API endpoint needs touching. The schema swaps a now-vacuous boolean check for a continuous, more honest stat.

**Tech Stack:** Python 3.12, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-01-terrain-driven-pond-sizing-design.md`

## Global Constraints

- **`recommend_pond_dimensions` and `PondRecommendation` in `domain/pond.py` are not modified** — they remain a valid, independently-tested utility; every existing test in `backend/tests/test_pond.py` must keep passing unchanged.
- **`compute_recommendation_fields`'s signature does not change** (`lat, lon, bbox, catchment_area_m2, achievable_volume_m3_by_depth`) — `api/recommend.py` and `api/analyze_contour.py` need no changes.
- **Site selection is out of scope** — `domain/catchment.py`'s `_find_depressions`/`_select_pond_site` are untouched.
- **No frontend changes.**
- **`annual_runoff_capture_fraction` follows the same nullable convention `fits_available_land` already uses**: a real fraction when computable, `None` when not (here: only when `runoff_volume_m3` is exactly 0, to avoid division by zero) — never a false value standing in for "unknown."

---

### Task 1: `size_pond_from_terrain_capacity` in `domain/pond.py`

**Files:**
- Modify: `backend/app/domain/pond.py`
- Modify: `backend/tests/test_pond.py`

**Interfaces:**
- Consumes: the existing `PondOption` dataclass (`depth_m: float`, `surface_area_m2: float`, `side_length_m: float`), unchanged.
- Produces: `size_pond_from_terrain_capacity(achievable_volume_m3_by_depth: dict[float, float]) -> list[PondOption]`. Task 2 imports and calls this from `services/recommendation.py`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_pond.py`, after the existing tests, and extend the import line at the top of the file:

```python
from app.domain.pond import CANDIDATE_DEPTHS_M, recommend_pond_dimensions, size_pond_from_terrain_capacity
```

```python
def test_size_pond_from_terrain_capacity_derives_area_from_each_depths_own_volume():
    options = size_pond_from_terrain_capacity({2.0: 4000.0, 3.0: 9000.0})
    by_depth = {o.depth_m: o for o in options}

    assert by_depth[2.0].surface_area_m2 == pytest.approx(2000.0)
    assert by_depth[2.0].side_length_m == pytest.approx(2000.0**0.5)
    assert by_depth[3.0].surface_area_m2 == pytest.approx(3000.0)
    assert by_depth[3.0].side_length_m == pytest.approx(3000.0**0.5)


def test_size_pond_from_terrain_capacity_options_are_independent_not_scaled_from_one_target():
    # Unlike recommend_pond_dimensions (one shared target -> area is
    # always exactly inversely proportional to depth), here each depth
    # has its own achievable volume, so a deeper option's area need not
    # be smaller -- it can even be larger, if the terrain holds
    # proportionally more at that depth. This distinguishes genuinely
    # independent per-depth sizing from a shared target in disguise.
    options = size_pond_from_terrain_capacity({2.0: 4000.0, 4.0: 12000.0})
    by_depth = {o.depth_m: o for o in options}

    assert by_depth[2.0].surface_area_m2 == pytest.approx(2000.0)
    assert by_depth[4.0].surface_area_m2 == pytest.approx(3000.0)
    assert by_depth[4.0].surface_area_m2 > by_depth[2.0].surface_area_m2


def test_size_pond_from_terrain_capacity_returns_options_sorted_by_depth():
    options = size_pond_from_terrain_capacity({4.0: 8000.0, 2.0: 4000.0, 3.0: 6000.0})
    assert [o.depth_m for o in options] == [2.0, 3.0, 4.0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `backend/`, venv active): `pytest tests/test_pond.py -k terrain_capacity -v`
Expected: FAIL — `ImportError: cannot import name 'size_pond_from_terrain_capacity'`

- [ ] **Step 3: Implement `size_pond_from_terrain_capacity`**

In `backend/app/domain/pond.py`, add this function at the end of the file (after `recommend_pond_dimensions`):

```python
def size_pond_from_terrain_capacity(
    achievable_volume_m3_by_depth: dict[float, float],
) -> list[PondOption]:
    """Back-solves a flat square footprint at each candidate depth from
    the site's own real terrain-holding capacity at that depth
    (domain/catchment.py's flood-fill), rather than an aspirational
    demand target. This answers a different question than
    recommend_pond_dimensions above: not "how big must the pond be to
    capture a year's runoff" but "how big can the pond actually be at
    this site" -- the two diverge whenever the catchment is large enough
    that capturing its full annual runoff would mean an unrealistic,
    reservoir-scale pond (see docs/DECISIONS.md D-007). This is the
    app's primary pond-sizing entry point (see services/recommendation.py);
    recommend_pond_dimensions remains available for a target-volume use
    case, but is no longer how the app's own recommendation is sized.
    """
    return [
        PondOption(
            depth_m=depth,
            surface_area_m2=(area := volume / depth),
            side_length_m=area**0.5,
        )
        for depth, volume in sorted(achievable_volume_m3_by_depth.items())
    ]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_pond.py -v`
Expected: PASS — every test in the file, including all pre-existing `recommend_pond_dimensions` tests (untouched, still valid).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/pond.py backend/tests/test_pond.py
git commit -m "Add size_pond_from_terrain_capacity: size ponds from real terrain capacity, not a runoff-capture target"
```

---

### Task 2: Wire terrain-driven sizing into the recommendation response

**Files:**
- Modify: `backend/app/schemas/recommend.py`
- Modify: `backend/app/services/recommendation.py`

**Interfaces:**
- Consumes: `size_pond_from_terrain_capacity` (Task 1).
- Produces: `PondOptionOut` loses `fits_terrain_capacity`, gains `annual_runoff_capture_fraction: float | None`. `compute_recommendation_fields`'s signature is unchanged.

- [ ] **Step 1: Update `PondOptionOut`**

In `backend/app/schemas/recommend.py`, replace:

```python
class PondOptionOut(BaseModel):
    depth_m: float
    surface_area_m2: float
    side_length_m: float
    # None when available-land data couldn't be determined (e.g. the
    # Overpass API was unreachable) -- absence of an answer, not "false".
    fits_available_land: bool | None
    # None when the terrain's achievable volume at this depth couldn't be
    # determined -- same convention as fits_available_land.
    fits_terrain_capacity: bool | None
```

with:

```python
class PondOptionOut(BaseModel):
    depth_m: float
    surface_area_m2: float
    side_length_m: float
    # None when available-land data couldn't be determined (e.g. the
    # Overpass API was unreachable) -- absence of an answer, not "false".
    fits_available_land: bool | None
    # How much of a typical year's catchment runoff this depth's
    # terrain-sized pond actually captures (e.g. 0.15 = 15%). None only
    # when runoff_volume_m3 is exactly 0, to avoid dividing by zero.
    annual_runoff_capture_fraction: float | None
```

- [ ] **Step 2: Update `compute_recommendation_fields`**

In `backend/app/services/recommendation.py`, replace the import:

```python
from app.domain.pond import recommend_pond_dimensions
```

with:

```python
from app.domain.pond import size_pond_from_terrain_capacity
```

Then replace:

```python
    pond = recommend_pond_dimensions(target_storage_m3=runoff.runoff_volume_m3)
    available_land_m2 = _get_available_land_hectares(bbox)

    return RecommendationFieldsOut(
        average_annual_rainfall_mm=rainfall.average_annual_mm,
        runoff_volume_m3=runoff.runoff_volume_m3,
        runoff_coefficient=runoff.runoff_coefficient,
        pond_options=[
            PondOptionOut(
                depth_m=o.depth_m,
                surface_area_m2=o.surface_area_m2,
                side_length_m=o.side_length_m,
                fits_available_land=(o.surface_area_m2 <= available_land_m2) if available_land_m2 is not None else None,
                fits_terrain_capacity=(
                    achievable_volume_m3_by_depth[o.depth_m] >= runoff.runoff_volume_m3
                    if o.depth_m in achievable_volume_m3_by_depth
                    else None
                ),
            )
            for o in pond.options
        ],
        available_land_hectares=(available_land_m2 / 10_000) if available_land_m2 is not None else None,
    )
```

with:

```python
    pond_options = size_pond_from_terrain_capacity(achievable_volume_m3_by_depth)
    available_land_m2 = _get_available_land_hectares(bbox)

    return RecommendationFieldsOut(
        average_annual_rainfall_mm=rainfall.average_annual_mm,
        runoff_volume_m3=runoff.runoff_volume_m3,
        runoff_coefficient=runoff.runoff_coefficient,
        pond_options=[
            PondOptionOut(
                depth_m=o.depth_m,
                surface_area_m2=o.surface_area_m2,
                side_length_m=o.side_length_m,
                fits_available_land=(o.surface_area_m2 <= available_land_m2) if available_land_m2 is not None else None,
                annual_runoff_capture_fraction=(
                    achievable_volume_m3_by_depth[o.depth_m] / runoff.runoff_volume_m3
                    if runoff.runoff_volume_m3 > 0
                    else None
                ),
            )
            for o in pond_options
        ],
        available_land_hectares=(available_land_m2 / 10_000) if available_land_m2 is not None else None,
    )
```

- [ ] **Step 3: Confirm nothing else constructs `PondOptionOut` or calls `recommend_pond_dimensions` from this call site**

Run: `grep -rn "PondOptionOut(\|fits_terrain_capacity" backend/`
Expected: the only `PondOptionOut(` construction is the one just edited in `services/recommendation.py`; no remaining reference to `fits_terrain_capacity` anywhere (schema, service, or any test) — a leftover reference would be a stale field access.

- [ ] **Step 4: Run the full backend test suite**

Run: `pytest -q`
Expected: PASS — no test constructs `PondOptionOut` or calls `compute_recommendation_fields` directly (per `docs/ARCHITECTURE.md`, this orchestration layer is verified live via its two endpoint callers, not unit-tested directly — Task 4 covers that).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/recommend.py backend/app/services/recommendation.py
git commit -m "Size pond options from terrain capacity instead of a runoff-capture target"
```

---

### Task 3: Record the decision in `docs/DECISIONS.md`

**Files:**
- Modify: `docs/DECISIONS.md`

**Interfaces:** none — documentation only.

- [ ] **Step 1: Append the new entry**

The file currently ends with D-006's "Impact" paragraph (no trailing separator after it). Append a separator and the new entry:

```markdown

---

## D-007: Pond sizing — demand-driven (100% of annual runoff) to supply-driven (terrain flood-fill capacity)

Date: 2026-09-01
Status: Accepted

**Context:** `domain/pond.py`'s `recommend_pond_dimensions` targeted a storage volume equal to 100% of one year's estimated catchment runoff (`domain/runoff.py`'s coefficient method), then back-solved a flat square footprint at each candidate depth. Once depression-preferred site selection (see the catchment/pond-volume improvements plan, 2026-09-01) started reliably landing on realistically-sized catchments near the top of the documented 1-50ha range, this produced reservoir-scale pond dimensions in the live app — e.g. a 213.7m × 213.7m × 2m pond (~91,000 m³) for a 25.8ha catchment — confirmed by the user testing the deployed app directly. The catchment area itself was not the problem (well within the documented realistic range); the demand target (capture 100% of annual runoff from tens of hectares in a single small pond) was.

**Decision:** Switch the app's primary pond-sizing path to supply-driven: each candidate depth's volume is that depth's own real terrain-holding capacity (`domain/catchment.py`'s flood-fill, `achievable_volume_m3_by_depth`), computed via a new `domain/pond.py` function, `size_pond_from_terrain_capacity`. The existing `recommend_pond_dimensions` (demand-target-driven) is kept, unmodified, as an available utility for a target-volume use case, but is no longer how the app's own recommendation is sized. The `PondOptionOut` schema's `fits_terrain_capacity` boolean (added in the prior plan, now vacuous by construction once sizing IS terrain capacity) is replaced with `annual_runoff_capture_fraction`, a continuous stat showing how much of a typical year's runoff each depth option actually captures.

**Rationale:** A sibling reference project (`virtualvasu/contour-detection-service`) independently arrived at the same supply-driven model — flood-fill the real terrain, cap at a realistic depth, size the pond to what the land can actually hold — and never produces reservoir-scale numbers regardless of catchment area, since the bound is physical, not an arbitrary capture target. This matches the user's own explicit priority throughout this project: physical/hydrological correctness over convenient implementation. Site selection itself is unaffected by this decision — only how the already-selected site's pond gets sized.

**Impact:** `domain/pond.py` gains `size_pond_from_terrain_capacity`; `recommend_pond_dimensions`/`PondRecommendation` and their existing tests are unchanged. `services/recommendation.py` calls the new function instead of the old one; its own public signature is unchanged, so neither `api/recommend.py` nor `api/analyze_contour.py` needed changes. `schemas/recommend.py`'s `PondOptionOut` loses `fits_terrain_capacity`, gains `annual_runoff_capture_fraction: float | None`. No frontend changes (the new field isn't rendered yet, same deferral as the prior plan).
```

- [ ] **Step 2: Commit**

```bash
git add docs/DECISIONS.md
git commit -m "Record D-007: switch pond sizing to terrain-capacity-driven"
```

---

### Task 4: Live verification

**Files:** none (verification only)

**Interfaces:** none — exercises the whole change end to end against the real backend.

- [ ] **Step 1: Rebuild and restart the backend**

```bash
docker compose build api
docker compose up -d api
```

Wait for `curl -s http://localhost:8000/health` to return `{"status":"ok"}` before continuing.

- [ ] **Step 2: Re-run the KMZ upload verification**

```bash
curl -s -X POST http://localhost:8000/analyzeContour -F "file=@<path-to-sample.kmz>" -o /tmp/kmz_response.json -w "HTTP %{http_code}\n"
python -c "
import json
d = json.load(open('/tmp/kmz_response.json'))
print('catchment ha:', d['catchment_area_hectares'])
print('pond_options:')
print(json.dumps(d['pond_options'], indent=2))
"
```

Expected: HTTP 200. Each `pond_options` entry now has `annual_runoff_capture_fraction` (not `fits_terrain_capacity`), and the `surface_area_m2`/`side_length_m` values are dramatically smaller than the previous run (no longer ~213m/~174m/~151m squares for this file) — sanity-check the new side lengths are on the order of tens of metres or less, not hundreds, for a small farm-pond-scale recommendation.

- [ ] **Step 3: Re-run the click-map verification**

```bash
curl -s -X POST http://localhost:8000/villages -H "Content-Type: application/json" -d '{"lat": 21.19, "lon": 81.3}' -o /tmp/village.json -w "HTTP %{http_code}\n"
python -c "import json; print(json.load(open('/tmp/village.json'))['id'])"
```

Take the printed `id`, then:

```bash
curl -s -X POST "http://localhost:8000/villages/<id>/recommend" -o /tmp/recommend.json -w "HTTP %{http_code}\n"
python -c "
import json
d = json.load(open('/tmp/recommend.json'))
print('rainfall mm/yr:', d['average_annual_rainfall_mm'])
print('runoff m3/yr:', d['runoff_volume_m3'])
print('pond_options:')
print(json.dumps(d['pond_options'], indent=2))
"
```

Expected: HTTP 200. Pond dimensions realistic (not the previous ~290m/~237m/~205m squares). Each option's `annual_runoff_capture_fraction` present and, given the site's large catchment relative to a small terrain-bounded pond, likely a small fraction (well under 1.0) — confirming the pond no longer claims to capture the full year's runoff, which is the whole point of this fix.

- [ ] **Step 4: Confirm no server errors**

```bash
docker logs village-map-selection-api-1 --since 5m | grep -iE "error|exception|traceback" | grep -v "Overpass\|overpass"
```

Expected: no output (or only the already-known, unrelated Overpass-unreachable degradation if that environment quirk is still present — not a new error).

- [ ] **Step 5: Run the full backend test suite one final time**

```bash
cd backend && DATABASE_URL=postgresql+psycopg://hydrosage:hydrosage@localhost:5432/hydrosage OBJECT_STORAGE_ENDPOINT=localhost:9000 REDIS_URL=redis://localhost:6379/0 python -m pytest -q
```

Expected: all tests pass, 0 failures.

- [ ] **Step 6: Report**

Summarize the before/after pond dimensions for both verified sites, confirming they now look plausible for a farm/community pond.

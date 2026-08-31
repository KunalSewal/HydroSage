# Catchment, Pond-Volume, and KML-Fidelity Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring three improvements from a comparable reference project into HydroSage's backend: prefer real topographic depressions when selecting a pond site (not just high-accumulation points), check the chosen site's terrain-grounded holding capacity against the existing runoff-driven pond-size target, and give the KML-upload flow full KMZ support with original-precision contour display.

**Architecture:** All changes are backend-only, in `backend/app/`. Site selection and terrain-capacity checking extend `domain/catchment.py` (still built on `pysheds`' D8 pipeline — no replacement of the flow-routing engine). The new pond-volume check flows through the existing `services/recommendation.py` orchestration layer and `schemas/recommend.py`, mirroring how `fits_available_land` already works. KML/KMZ parsing changes are contained to `infrastructure/kml_parser.py` and the one endpoint that calls it.

**Tech Stack:** Python 3.12, FastAPI, `pysheds` (D8 flow routing), `scipy.ndimage` (depression detection, flood-fill labeling), `numpy`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-01-catchment-pond-improvements-design.md`

## Global Constraints

- **No replacement of `pysheds`** with a hand-rolled D8 implementation, and **no switch to UTM reprojection** for cell-size/area math — both explicitly out of scope per the spec.
- **No changes** to `domain/runoff.py`, `domain/rainfall.py`, `domain/land_availability.py`, any `infrastructure/*_client.py`, either cache's existing behavior beyond the one fix in Task 2, the frontend, or the DB schema.
- **Both flows** (click-map live DEM and KML upload) get every change in this plan — neither is flow-specific except Task 4, which is inherently KML-only (a live DEM has no "original lines" to preserve).
- **`fits_terrain_capacity` follows the same nullable convention `fits_available_land` already uses**: `true`/`false` when computable, `null` when it couldn't be determined — never a false negative standing in for "unknown."
- **No frontend changes** — the API response gains new fields; displaying them is explicitly out of scope for this plan.

---

### Task 1: Depression-aware pond-site selection

**Files:**
- Modify: `backend/app/domain/catchment.py`
- Modify: `backend/tests/test_catchment.py`

**Interfaces:**
- Consumes: nothing new from outside this file.
- Produces: `_Candidate` gains a new field `is_depression: bool = False` (default keeps every existing call site valid). New function `_find_depressions(elevation: np.ndarray, margin_rows: int, margin_cols: int) -> np.ndarray` (boolean mask, same shape as `elevation`). `_select_pond_site`'s signature is unchanged; its selection behavior changes as described below. `analyze_catchment`'s public signature and `CatchmentResult` shape are unchanged by this task (Task 2 extends `CatchmentResult`).

- [ ] **Step 1: Write the failing tests for `_find_depressions`**

Add to `backend/tests/test_catchment.py`, in a new section after the existing `_sample_candidates` tests:

```python
# ---- _find_depressions: local minima on the RAW (unconditioned) grid ----


def test_find_depressions_marks_a_true_local_minimum():
    elevation = np.full((20, 20), 100.0)
    elevation[10, 10] = 50.0  # a bowl -- lower than all 8 neighbors

    depressions = _find_depressions(elevation, margin_rows=2, margin_cols=2)

    assert depressions[10, 10]
    assert not depressions[10, 11]  # a flat neighbor, not itself a local minimum


def test_find_depressions_excludes_a_uniform_slope():
    y, x = np.mgrid[0:20, 0:20]
    elevation = (x + y).astype(np.float64)  # no local minima anywhere in the interior

    depressions = _find_depressions(elevation, margin_rows=2, margin_cols=2)

    assert not depressions[10, 10]


def test_find_depressions_respects_the_margin():
    elevation = np.full((20, 20), 100.0)
    elevation[0, 0] = 1.0  # a real depression, but right on the edge

    depressions = _find_depressions(elevation, margin_rows=3, margin_cols=3)

    assert not depressions[0, 0]
```

Add the import at the top of `backend/tests/test_catchment.py` (extend the existing `from app.domain.catchment import (...)` block):

```python
from app.domain.catchment import (
    MAX_CATCHMENT_AREA_M2,
    MIN_CATCHMENT_AREA_M2,
    _Candidate,
    _find_depressions,
    _sample_candidates,
    _select_pond_site,
    analyze_catchment,
)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `backend/`, venv active): `pytest tests/test_catchment.py -k find_depressions -v`
Expected: FAIL — `ImportError: cannot import name '_find_depressions'`

- [ ] **Step 3: Implement `_find_depressions`**

In `backend/app/domain/catchment.py`, add `from scipy import ndimage` to the imports (alongside the existing `import numpy as np`), and add this function after `_cell_area_m2`:

```python
def _find_depressions(elevation: np.ndarray, margin_rows: int, margin_cols: int) -> np.ndarray:
    """True where a cell has no neighbor (of its 8 neighbors) that's
    strictly lower -- a local low point on the RAW, unconditioned
    elevation grid. Must run on this raw grid, not the pit-filled one:
    pysheds' fill_pits/fill_depressions/resolve_flats exist specifically
    to eliminate these for flow routing, so by the time accumulation is
    computed in analyze_catchment, real depressions are already gone
    from that grid."""
    local_min = ndimage.minimum_filter(elevation, size=3, mode="nearest")
    is_depression = elevation <= local_min

    is_depression[:margin_rows, :] = False
    is_depression[elevation.shape[0] - margin_rows :, :] = False
    is_depression[:, :margin_cols] = False
    is_depression[:, elevation.shape[1] - margin_cols :] = False
    return is_depression
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_catchment.py -k find_depressions -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Write the failing tests for depression-preferring selection**

Add to `backend/tests/test_catchment.py`, after the existing `_select_pond_site` tests:

```python
def test_select_pond_site_prefers_a_depression_over_higher_accumulation():
    candidates = [
        _Candidate(row=0, col=0, accumulation=100.0, is_depression=False),  # in range, higher accumulation
        _Candidate(row=1, col=1, accumulation=20.0, is_depression=True),  # in range, a real depression
    ]
    mid = (MIN_CATCHMENT_AREA_M2 + MAX_CATCHMENT_AREA_M2) / 2
    areas = {(0, 0): (None, mid), (1, 1): (None, mid)}

    chosen, _mask, _area = _select_pond_site(candidates, lambda c: areas[(c.row, c.col)])

    assert chosen.row == 1 and chosen.col == 1


def test_select_pond_site_falls_back_to_non_depression_when_no_depression_fits():
    candidates = [
        _Candidate(row=0, col=0, accumulation=100.0, is_depression=False),  # in range
        _Candidate(row=1, col=1, accumulation=20.0, is_depression=True),  # a depression, but way too big
    ]
    mid = (MIN_CATCHMENT_AREA_M2 + MAX_CATCHMENT_AREA_M2) / 2
    areas = {(0, 0): (None, mid), (1, 1): (None, MAX_CATCHMENT_AREA_M2 * 10)}

    chosen, _mask, _area = _select_pond_site(candidates, lambda c: areas[(c.row, c.col)])

    assert chosen.row == 0 and chosen.col == 0


def test_select_pond_site_only_traces_each_candidate_once():
    # Regression guard: preferring depressions must not re-run the (expensive,
    # real) catchment trace for a candidate already checked during the
    # depression-only pass.
    candidates = [_Candidate(row=1, col=1, accumulation=20.0, is_depression=True)]
    mid = (MIN_CATCHMENT_AREA_M2 + MAX_CATCHMENT_AREA_M2) / 2
    call_count = 0

    def catchment_for(candidate):
        nonlocal call_count
        call_count += 1
        return None, mid

    _select_pond_site(candidates, catchment_for)

    assert call_count == 1
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `pytest tests/test_catchment.py -k "prefers_a_depression or falls_back_to_non_depression or traces_each_candidate_once" -v`
Expected: FAIL — `TypeError: _Candidate.__init__() got an unexpected keyword argument 'is_depression'`

- [ ] **Step 7: Implement the `is_depression` field and rewrite `_select_pond_site`**

In `backend/app/domain/catchment.py`, change the import line `from dataclasses import dataclass` to:

```python
from dataclasses import dataclass, replace
```

Change the `_Candidate` dataclass:

```python
@dataclass(frozen=True)
class _Candidate:
    row: int
    col: int
    accumulation: float
    is_depression: bool = False
```

Replace the whole `_select_pond_site` function with:

```python
def _select_pond_site(
    candidates: list[_Candidate],
    catchment_for: Callable[[_Candidate], tuple[np.ndarray, float]],
) -> tuple[_Candidate, np.ndarray, float]:
    """Walks candidates highest-accumulation first, preferring a real
    depression (see _find_depressions) over a non-depression candidate
    whenever one fits the target area range -- a depression is where
    water naturally pools, a more physically grounded pond site than an
    arbitrary point on the accumulation-ranked list. Falls back to the
    best-fitting candidate overall (depression or not) if no depression
    candidate fits, then to whichever candidate's area is closest to the
    target range if nothing fits at all, rather than failing -- a traced
    catchment is still returned, it just couldn't be tuned to the target
    scale or a natural depression for this particular terrain.

    Each candidate's (expensive, real) catchment trace is memoized by
    position, so checking the depression subset first and then
    potentially the full list never re-traces the same candidate twice.
    """
    if not candidates:
        raise ValueError("no candidates to select a pond site from")

    cache: dict[tuple[int, int], tuple[np.ndarray, float]] = {}

    def traced(candidate: _Candidate) -> tuple[np.ndarray, float]:
        key = (candidate.row, candidate.col)
        if key not in cache:
            cache[key] = catchment_for(candidate)
        return cache[key]

    def first_in_range(pool: list[_Candidate]) -> tuple[_Candidate, np.ndarray, float] | None:
        for candidate in pool:
            mask, area_m2 = traced(candidate)
            if MIN_CATCHMENT_AREA_M2 <= area_m2 <= MAX_CATCHMENT_AREA_M2:
                return candidate, mask, area_m2
        return None

    depression_candidates = [c for c in candidates if c.is_depression]
    if depression_candidates:
        found = first_in_range(depression_candidates)
        if found is not None:
            return found

    found = first_in_range(candidates)
    if found is not None:
        return found

    best_fallback: tuple[float, _Candidate, np.ndarray, float] | None = None
    for candidate in candidates:
        mask, area_m2 = traced(candidate)
        distance = (
            MIN_CATCHMENT_AREA_M2 - area_m2 if area_m2 < MIN_CATCHMENT_AREA_M2 else area_m2 - MAX_CATCHMENT_AREA_M2
        )
        if best_fallback is None or distance < best_fallback[0]:
            best_fallback = (distance, candidate, mask, area_m2)

    logger.info("no sampled candidate's catchment fit the target area range; using the closest fallback")
    _distance, candidate, mask, area_m2 = best_fallback
    return candidate, mask, area_m2
```

In `analyze_catchment`, insert depression tagging right after candidates are sampled:

```python
    candidates = _sample_candidates(acc, margin_rows, margin_cols)
    depression_mask = _find_depressions(elevation, margin_rows, margin_cols)
    candidates = [replace(c, is_depression=bool(depression_mask[c.row, c.col])) for c in candidates]
    candidate, catchment_mask, area_m2 = _select_pond_site(candidates, catchment_for)
```

(This replaces the existing single line `candidate, catchment_mask, area_m2 = _select_pond_site(candidates, catchment_for)` — the `candidates = _sample_candidates(...)` line above it already exists; just insert the two new lines between them.)

- [ ] **Step 8: Run the tests to verify they pass**

Run: `pytest tests/test_catchment.py -v`
Expected: PASS — every test in the file, including the pre-existing ones (they construct `_Candidate` without `is_depression`, which defaults to `False`, so their behavior is unchanged).

- [ ] **Step 9: Commit**

```bash
git add backend/app/domain/catchment.py backend/tests/test_catchment.py
git commit -m "Prefer real topographic depressions when selecting a pond site"
```

---

### Task 2: Terrain-grounded achievable pond volume

**Files:**
- Modify: `backend/app/domain/catchment.py`
- Modify: `backend/app/infrastructure/catchment_cache.py`
- Modify: `backend/tests/test_catchment.py`
- Modify: `backend/tests/test_catchment_cache.py`

**Interfaces:**
- Consumes: `CANDIDATE_DEPTHS_M` from `app.domain.pond` (existing constant, `(2.0, 3.0, 4.0)`).
- Produces: new function `_flood_fill_achievable_volume(elevation: np.ndarray, cell_area_m2: float, site_row: int, site_col: int, catchment_mask: np.ndarray, depths_m: tuple[float, ...]) -> dict[float, float]`. `CatchmentResult` gains a new required field `achievable_volume_m3_by_depth: dict[float, float]`. Task 3 consumes this field from `CatchmentResult` via `api/recommend.py` and `api/analyze_contour.py`.

- [ ] **Step 1: Write the failing test for `_flood_fill_achievable_volume`**

Add to `backend/tests/test_catchment.py`, after the `_find_depressions` tests:

```python
# ---- _flood_fill_achievable_volume: real terrain shape -> achievable storage ----


def test_flood_fill_achievable_volume_on_a_flat_bottomed_bowl():
    # A perfectly flat-bottomed 10x10 bowl, 1m deep, surrounded by high walls.
    # Flooding it to 1m should hold very close to its full flat-bottom volume
    # (area * depth); flooding deeper isn't possible since the walls are high
    # enough not to spill within this test's candidate depths.
    elevation = np.full((30, 30), 100.0)
    elevation[10:20, 10:20] = 0.0  # a 10x10 flat floor at elevation 0
    catchment_mask = np.ones((30, 30), dtype=bool)
    cell_area_m2 = 100.0  # 10m x 10m cells -> the bowl floor is 100 * 100 = 10,000 m^2

    volumes = _flood_fill_achievable_volume(
        elevation, cell_area_m2, site_row=15, site_col=15, catchment_mask=catchment_mask, depths_m=(1.0,)
    )

    assert volumes[1.0] == pytest.approx(10_000 * 1.0, rel=0.05)


def test_flood_fill_achievable_volume_caps_when_the_flood_spills():
    # A shallow bowl that spills (reaches the raster edge) well before the
    # requested depth -- every depth at or past the spill point must report
    # the same capped volume, since the terrain can't hold more without an
    # embankment higher than its own natural rim.
    elevation = np.full((10, 10), 100.0)
    elevation[4:6, 4:6] = 99.0  # only 1m of relief before the flood reaches the raster edge
    catchment_mask = np.ones((10, 10), dtype=bool)

    volumes = _flood_fill_achievable_volume(
        elevation, cell_area_m2=1.0, site_row=4, site_col=4, catchment_mask=catchment_mask, depths_m=(2.0, 4.0)
    )

    assert volumes[2.0] == volumes[4.0]  # capped at the same achievable volume
    assert volumes[4.0] > 0


def test_flood_fill_achievable_volume_returns_an_entry_for_every_requested_depth():
    elevation = np.full((20, 20), 100.0)
    elevation[8:12, 8:12] = 90.0
    catchment_mask = np.ones((20, 20), dtype=bool)

    volumes = _flood_fill_achievable_volume(
        elevation, cell_area_m2=4.0, site_row=10, site_col=10, catchment_mask=catchment_mask, depths_m=(2.0, 3.0, 4.0)
    )

    assert set(volumes.keys()) == {2.0, 3.0, 4.0}
    assert volumes[2.0] <= volumes[3.0] <= volumes[4.0]
```

Extend the test file's import line for this new name too:

```python
from app.domain.catchment import (
    MAX_CATCHMENT_AREA_M2,
    MIN_CATCHMENT_AREA_M2,
    _Candidate,
    _find_depressions,
    _flood_fill_achievable_volume,
    _sample_candidates,
    _select_pond_site,
    analyze_catchment,
)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_catchment.py -k flood_fill -v`
Expected: FAIL — `ImportError: cannot import name '_flood_fill_achievable_volume'`

- [ ] **Step 3: Implement `_flood_fill_achievable_volume`**

In `backend/app/domain/catchment.py`, add this constant near the top (alongside `CANDIDATE_GRID_DIVISIONS`/`LOCAL_WINDOW_RADIUS`):

```python
FLOOD_STEP_COUNT = 40  # resolution of the flood-fill volume integration
```

Add the import `from app.domain.pond import CANDIDATE_DEPTHS_M` alongside the existing `from app.infrastructure.elevation_client import BoundingBox`.

Add this function after `_select_pond_site`:

```python
def _flood_fill_achievable_volume(
    elevation: np.ndarray,
    cell_area_m2: float,
    site_row: int,
    site_col: int,
    catchment_mask: np.ndarray,
    depths_m: tuple[float, ...],
) -> dict[float, float]:
    """For the chosen pond site, raises a flood level step by step from the
    site's own base elevation (on the RAW, unconditioned grid -- the same
    reason _find_depressions doesn't use the pit-filled grid) and
    integrates flooded-area-vs-elevation (trapezoidal) into an achievable
    volume at each of `depths_m` metres above that base. The flood is
    constrained to the site's own traced catchment and stops early if it
    would spill past that catchment's extent or the raster's edge -- once
    that happens, every deeper depth gets the same capped volume, since
    the terrain physically can't hold more without an embankment higher
    than its own natural rim.
    """
    base_elevation = float(elevation[site_row, site_col])
    max_depth = max(depths_m)
    step = max_depth / FLOOD_STEP_COUNT

    prev_area_m2 = 0.0
    prev_level = base_elevation
    volume_m3 = 0.0
    volume_at_depth: dict[float, float] = {}
    remaining = sorted(depths_m)
    spilled = False

    for i in range(FLOOD_STEP_COUNT + 1):
        level = base_elevation + min(i * step, max_depth)
        if not spilled:
            flooded = (elevation <= level) & catchment_mask
            labeled, _ = ndimage.label(flooded, structure=np.ones((3, 3)))
            site_label = labeled[site_row, site_col]
            region = (labeled == site_label) if site_label != 0 else np.zeros_like(flooded)
            touches_edge = (
                region[0, :].any() or region[-1, :].any() or region[:, 0].any() or region[:, -1].any()
            )
            spilled = touches_edge or region.sum() >= catchment_mask.sum()
            area_m2 = float(region.sum()) * cell_area_m2
            volume_m3 += (prev_area_m2 + area_m2) / 2.0 * (level - prev_level)
            prev_area_m2, prev_level = area_m2, level

        depth_here = level - base_elevation
        while remaining and depth_here >= remaining[0] - 1e-9:
            volume_at_depth[remaining.pop(0)] = volume_m3

    for depth in remaining:
        volume_at_depth[depth] = volume_m3
    return volume_at_depth
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_catchment.py -k flood_fill -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Wire the new field into `CatchmentResult` and `analyze_catchment`**

In `backend/app/domain/catchment.py`, change `CatchmentResult`:

```python
@dataclass(frozen=True)
class CatchmentResult:
    pond_lat: float
    pond_lon: float
    catchment_area_m2: float
    catchment_cell_count: int
    flow_accumulation_at_pond: float
    catchment_boundary: list[list[float]]  # [[lon, lat], ...], closed ring
    achievable_volume_m3_by_depth: dict[float, float]
```

At the end of `analyze_catchment`, replace:

```python
    pond_lon, pond_lat = affine * (candidate.col + 0.5, candidate.row + 0.5)
    cell_count = int(catchment_mask.sum())
    boundary = _mask_to_boundary_ring(catchment_mask, grid)

    return CatchmentResult(
        pond_lat=float(pond_lat),
        pond_lon=float(pond_lon),
        catchment_area_m2=area_m2,
        catchment_cell_count=cell_count,
        flow_accumulation_at_pond=candidate.accumulation,
        catchment_boundary=boundary,
    )
```

with:

```python
    pond_lon, pond_lat = affine * (candidate.col + 0.5, candidate.row + 0.5)
    cell_count = int(catchment_mask.sum())
    boundary = _mask_to_boundary_ring(catchment_mask, grid)
    achievable_volume = _flood_fill_achievable_volume(
        elevation, cell_area_m2, candidate.row, candidate.col, catchment_mask, CANDIDATE_DEPTHS_M
    )

    return CatchmentResult(
        pond_lat=float(pond_lat),
        pond_lon=float(pond_lon),
        catchment_area_m2=area_m2,
        catchment_cell_count=cell_count,
        flow_accumulation_at_pond=candidate.accumulation,
        catchment_boundary=boundary,
        achievable_volume_m3_by_depth=achievable_volume,
    )
```

- [ ] **Step 6: Update the existing `analyze_catchment` tests and typecheck**

`test_analyze_catchment_returns_a_realistically_sized_pond_catchment` and `test_analyze_catchment_still_returns_a_boundary_and_positive_area` in `backend/tests/test_catchment.py` call `analyze_catchment(elevation, bbox)` and only inspect existing fields — they need no changes. Confirm this by running:

Run: `pytest tests/test_catchment.py -v`
Expected: PASS — every test in the file.

- [ ] **Step 7: Fix the cache's float-key round-trip and update its test fixtures**

`CatchmentResult` is JSON-serialized for the Redis cache (`json.dumps(asdict(result))` / `CatchmentResult(**json.loads(payload))`). JSON object keys are always strings, so `achievable_volume_m3_by_depth`'s float keys (`2.0`, `3.0`, `4.0`) would silently come back as the strings `"2.0"`, `"3.0"`, `"4.0"` after a cache round-trip — a real type inconsistency between a cache-hit and a fresh computation. Fix `get()` in `backend/app/infrastructure/catchment_cache.py`:

Replace:

```python
        try:
            payload = raw.decode() if isinstance(raw, bytes) else raw
            return CatchmentResult(**json.loads(payload))
        except Exception:  # noqa: BLE001 -- a corrupted/stale entry must not break the request
            logger.warning("catchment cache entry unreadable, will recompute", exc_info=True)
            return None
```

with:

```python
        try:
            payload = raw.decode() if isinstance(raw, bytes) else raw
            data = json.loads(payload)
            data["achievable_volume_m3_by_depth"] = {
                float(depth): volume for depth, volume in data["achievable_volume_m3_by_depth"].items()
            }
            return CatchmentResult(**data)
        except Exception:  # noqa: BLE001 -- a corrupted/stale entry must not break the request
            logger.warning("catchment cache entry unreadable, will recompute", exc_info=True)
            return None
```

Update `backend/tests/test_catchment_cache.py`'s fixtures to include the new required field — replace:

```python
_RESULT = CatchmentResult(
    pond_lat=21.24,
    pond_lon=81.29,
    catchment_area_m2=19_613.75,
    catchment_cell_count=42,
    flow_accumulation_at_pond=999.0,
    catchment_boundary=[[81.28, 21.24], [81.29, 21.25], [81.28, 21.24]],
)
```

with:

```python
_RESULT = CatchmentResult(
    pond_lat=21.24,
    pond_lon=81.29,
    catchment_area_m2=19_613.75,
    catchment_cell_count=42,
    flow_accumulation_at_pond=999.0,
    catchment_boundary=[[81.28, 21.24], [81.29, 21.25], [81.28, 21.24]],
    achievable_volume_m3_by_depth={2.0: 5_000.0, 3.0: 6_500.0, 4.0: 7_000.0},
)
```

And in `test_different_villages_do_not_collide`, replace:

```python
    other = CatchmentResult(
        pond_lat=1.0, pond_lon=2.0, catchment_area_m2=1.0, catchment_cell_count=1,
        flow_accumulation_at_pond=1.0, catchment_boundary=[],
    )
```

with:

```python
    other = CatchmentResult(
        pond_lat=1.0, pond_lon=2.0, catchment_area_m2=1.0, catchment_cell_count=1,
        flow_accumulation_at_pond=1.0, catchment_boundary=[], achievable_volume_m3_by_depth={},
    )
```

- [ ] **Step 8: Run the cache tests to verify the round-trip now preserves float keys**

Run: `pytest tests/test_catchment_cache.py -v`
Expected: PASS — every test, including `test_put_then_get_round_trips_the_same_result` (which now exercises float-keyed dict equality — `CatchmentResult.__eq__` via `@dataclass` compares `{2.0: ...} == {2.0: ...}`, which fails if the cached side came back as `{"2.0": ...}` instead, so this test would have failed without the Step 7 fix).

- [ ] **Step 9: Commit**

```bash
git add backend/app/domain/catchment.py backend/app/infrastructure/catchment_cache.py backend/tests/test_catchment.py backend/tests/test_catchment_cache.py
git commit -m "Add terrain-grounded achievable pond volume via flood-fill"
```

---

### Task 3: Expose achievable volume as a pond-option check

**Files:**
- Modify: `backend/app/schemas/recommend.py`
- Modify: `backend/app/services/recommendation.py`
- Modify: `backend/app/api/recommend.py`
- Modify: `backend/app/api/analyze_contour.py`

**Interfaces:**
- Consumes: `CatchmentResult.achievable_volume_m3_by_depth` (Task 2).
- Produces: `compute_recommendation_fields` gains a new required parameter `achievable_volume_m3_by_depth: dict[float, float]`. `PondOptionOut` gains `fits_terrain_capacity: bool | None`.

- [ ] **Step 1: Add the new field to `PondOptionOut`**

In `backend/app/schemas/recommend.py`, replace:

```python
class PondOptionOut(BaseModel):
    depth_m: float
    surface_area_m2: float
    side_length_m: float
    # None when available-land data couldn't be determined (e.g. the
    # Overpass API was unreachable) -- absence of an answer, not "false".
    fits_available_land: bool | None
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
    # None when the terrain's achievable volume at this depth couldn't be
    # determined -- same convention as fits_available_land.
    fits_terrain_capacity: bool | None
```

- [ ] **Step 2: Thread the new parameter through `compute_recommendation_fields`**

In `backend/app/services/recommendation.py`, change the function signature and its body. Replace:

```python
def compute_recommendation_fields(
    lat: float, lon: float, bbox: BoundingBox, catchment_area_m2: float
) -> RecommendationFieldsOut:
```

with:

```python
def compute_recommendation_fields(
    lat: float,
    lon: float,
    bbox: BoundingBox,
    catchment_area_m2: float,
    achievable_volume_m3_by_depth: dict[float, float],
) -> RecommendationFieldsOut:
```

Replace the `pond_options=[...]` block inside the function's `return RecommendationFieldsOut(...)`:

```python
        pond_options=[
            PondOptionOut(
                depth_m=o.depth_m,
                surface_area_m2=o.surface_area_m2,
                side_length_m=o.side_length_m,
                fits_available_land=(o.surface_area_m2 <= available_land_m2) if available_land_m2 is not None else None,
            )
            for o in pond.options
        ],
```

with:

```python
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
```

- [ ] **Step 3: Update both callers**

In `backend/app/api/recommend.py`, replace:

```python
    fields = compute_recommendation_fields(centroid.y, centroid.x, bbox, catchment.catchment_area_m2)
```

with:

```python
    fields = compute_recommendation_fields(
        centroid.y, centroid.x, bbox, catchment.catchment_area_m2, catchment.achievable_volume_m3_by_depth
    )
```

In `backend/app/api/analyze_contour.py`, replace:

```python
    recommendation_fields = compute_recommendation_fields(
        centroid_lat, centroid_lon, bbox, result.catchment_area_m2
    )
```

with:

```python
    recommendation_fields = compute_recommendation_fields(
        centroid_lat, centroid_lon, bbox, result.catchment_area_m2, result.achievable_volume_m3_by_depth
    )
```

- [ ] **Step 4: Run the full backend test suite and typecheck**

Run: `pytest -q` (from `backend/`, venv active)
Expected: PASS — no test constructs `PondOptionOut` or calls `compute_recommendation_fields` directly (per `docs/ARCHITECTURE.md`, this orchestration layer is verified live via its two callers, not unit-tested directly — Task 5 covers that).

Run: `python -c "import app.main"` (from `backend/`, venv active, with `DATABASE_URL`/`OBJECT_STORAGE_ENDPOINT`/`REDIS_URL` overridden to `localhost` per `docs/PROJECT_STATUS.md`'s host-run instructions, or simply via `docker compose build api` if running everything in Docker)
Expected: no import/signature errors — confirms every call site's argument count matches the new signature.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/recommend.py backend/app/services/recommendation.py backend/app/api/recommend.py backend/app/api/analyze_contour.py
git commit -m "Check pond options against the terrain's actual achievable volume"
```

---

### Task 4: KMZ support and original-precision KML contour display

**Files:**
- Modify: `backend/app/infrastructure/kml_parser.py`
- Modify: `backend/app/api/analyze_contour.py`
- Create: `backend/tests/test_kml_parser.py`

**Interfaces:**
- Consumes: nothing new from other tasks.
- Produces: `parse_contour_kml`'s return type changes from `tuple[np.ndarray, BoundingBox]` to `tuple[np.ndarray, BoundingBox, list[ContourLine]]`. New public dataclass `ContourLine(elevation: float, points: list[tuple[float, float]])`. The `/analyzeContour` endpoint accepts `.kml` and `.kmz`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_kml_parser.py`:

```python
import io
import zipfile

import pytest

from app.infrastructure.kml_parser import ContourLine, parse_contour_kml

_SAMPLE_KML = b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>250</name>
      <LineString>
        <coordinates>74.60,19.06,0 74.61,19.06,0 74.61,19.07,0</coordinates>
      </LineString>
    </Placemark>
    <Placemark>
      <name>260</name>
      <LineString>
        <coordinates>74.60,19.08,0 74.61,19.08,0 74.61,19.09,0</coordinates>
      </LineString>
    </Placemark>
    <Placemark>
      <name>270</name>
      <LineString>
        <coordinates>74.60,19.10,0 74.61,19.10,0 74.61,19.11,0</coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>
"""


def _as_kmz(kml_bytes: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("doc.kml", kml_bytes)
    return buffer.getvalue()


def test_parse_contour_kml_returns_the_original_line_geometry():
    _elevation, _bbox, lines = parse_contour_kml(_SAMPLE_KML)

    assert lines == [
        ContourLine(elevation=250.0, points=[(74.60, 19.06), (74.61, 19.06), (74.61, 19.07)]),
        ContourLine(elevation=260.0, points=[(74.60, 19.08), (74.61, 19.08), (74.61, 19.09)]),
        ContourLine(elevation=270.0, points=[(74.60, 19.10), (74.61, 19.10), (74.61, 19.11)]),
    ]


def test_parse_contour_kml_still_produces_an_interpolated_grid():
    elevation, bbox, _lines = parse_contour_kml(_SAMPLE_KML, grid_size=20)

    assert elevation.shape == (20, 20)
    assert bbox.min_lon == pytest.approx(74.60)
    assert bbox.max_lat == pytest.approx(19.11)


def test_parse_contour_kml_accepts_a_kmz_archive():
    kmz_bytes = _as_kmz(_SAMPLE_KML)

    _elevation, _bbox, lines = parse_contour_kml(kmz_bytes)

    assert len(lines) == 3
    assert lines[0].elevation == 250.0


def test_parse_contour_kml_rejects_a_kmz_with_no_kml_inside():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "not a kml file")

    with pytest.raises(ValueError, match="kml"):
        parse_contour_kml(buffer.getvalue())


def test_parse_contour_kml_rejects_a_corrupted_zip_looking_file():
    corrupted = b"PK" + b"not actually a valid zip archive"

    with pytest.raises(ValueError, match="zip"):
        parse_contour_kml(corrupted)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_kml_parser.py -v`
Expected: FAIL — `ImportError: cannot import name 'ContourLine'` (and `parse_contour_kml` currently returns a 2-tuple, not a 3-tuple)

- [ ] **Step 3: Implement KMZ support and line-preserving parsing**

Replace the full contents of `backend/app/infrastructure/kml_parser.py` with:

```python
"""Parses a contour-line KML/KMZ (elevation contour lines as LineString
Placemarks) into both an interpolated elevation grid, matching the shape
ElevationClient.get_dem_for_bbox produces (so the same catchment analysis
can run on either input), and the original parsed line geometry, kept
separately so callers can display the KML's own precision instead of the
grid's lossy marching-squares re-trace (see analyze_contour.py).
"""

import io
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import griddata

from app.infrastructure.elevation_client import BoundingBox

_KML_NS_URI = "http://www.opengis.net/kml/2.2"
_KML_NS = {"kml": _KML_NS_URI}
DEFAULT_GRID_SIZE = 300


@dataclass(frozen=True)
class ContourLine:
    elevation: float
    points: list[tuple[float, float]]  # [(lon, lat), ...], in KML order


def _load_kml_bytes(raw: bytes) -> bytes:
    """Returns raw KML bytes, unzipping the first .kml entry if `raw` is a
    KMZ (a zip archive) rather than raw KML XML. Prefers an entry literally
    named doc.kml if present, matching common KMZ export conventions."""
    if raw[:2] != b"PK":
        return raw
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            kml_names = [name for name in archive.namelist() if name.lower().endswith(".kml")]
            if not kml_names:
                raise ValueError("KMZ archive does not contain a .kml file")
            kml_names.sort(key=lambda name: (name.lower() != "doc.kml", name))
            return archive.read(kml_names[0])
    except zipfile.BadZipFile as error:
        raise ValueError("file looks like a KMZ but is not a valid zip archive") from error


def _extract_contour_lines(kml_bytes: bytes) -> list[ContourLine]:
    root = ET.fromstring(kml_bytes)
    lines: list[ContourLine] = []

    for placemark in root.iter(f"{{{_KML_NS_URI}}}Placemark"):
        name_elem = placemark.find("kml:name", _KML_NS)
        if name_elem is None or name_elem.text is None:
            continue
        try:
            elevation = float(name_elem.text)
        except ValueError:
            continue

        coords_elem = placemark.find(".//kml:LineString/kml:coordinates", _KML_NS)
        if coords_elem is None or coords_elem.text is None:
            continue

        points: list[tuple[float, float]] = []
        for vertex in coords_elem.text.split():
            parts = vertex.split(",")
            if len(parts) < 2:
                continue
            lon, lat = float(parts[0]), float(parts[1])
            points.append((lon, lat))

        if len(points) >= 2:
            lines.append(ContourLine(elevation=elevation, points=points))

    return lines


def parse_contour_kml(
    kml_bytes: bytes, grid_size: int = DEFAULT_GRID_SIZE
) -> tuple[np.ndarray, BoundingBox, list[ContourLine]]:
    kml_bytes = _load_kml_bytes(kml_bytes)
    lines = _extract_contour_lines(kml_bytes)

    points = [(lon, lat, line.elevation) for line in lines for lon, lat in line.points]
    if len(points) < 3:
        raise ValueError("KML has too few contour points to interpolate a surface")

    lons = np.array([p[0] for p in points])
    lats = np.array([p[1] for p in points])
    elevations = np.array([p[2] for p in points])

    bbox = BoundingBox(
        min_lon=float(lons.min()),
        min_lat=float(lats.min()),
        max_lon=float(lons.max()),
        max_lat=float(lats.max()),
    )

    grid_lon = np.linspace(bbox.min_lon, bbox.max_lon, grid_size)
    grid_lat = np.linspace(bbox.max_lat, bbox.min_lat, grid_size)  # row 0 = north
    mesh_lon, mesh_lat = np.meshgrid(grid_lon, grid_lat)

    elevation_grid = griddata((lons, lats), elevations, (mesh_lon, mesh_lat), method="linear")

    # Linear interpolation leaves NaN outside the convex hull of the input
    # points; fill those with nearest-neighbor so the grid has no gaps.
    nan_mask = np.isnan(elevation_grid)
    if nan_mask.any():
        nearest = griddata((lons, lats), elevations, (mesh_lon, mesh_lat), method="nearest")
        elevation_grid[nan_mask] = nearest[nan_mask]

    return elevation_grid, bbox, lines
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_kml_parser.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Update `analyze_contour.py` to accept KMZ and display original lines**

Replace the full contents of `backend/app/api/analyze_contour.py` with:

```python
from fastapi import APIRouter, HTTPException, UploadFile

from app.domain.catchment import analyze_catchment
from app.infrastructure.kml_parser import DEFAULT_GRID_SIZE, parse_contour_kml
from app.schemas.catchment import BoundingBoxOut, CatchmentAnalysisOut, catchment_fields
from app.services.recommendation import compute_recommendation_fields

router = APIRouter(tags=["analyze-contour"])


@router.post("/analyzeContour", response_model=CatchmentAnalysisOut)
async def analyze_contour(file: UploadFile):
    if not file.filename or not file.filename.lower().endswith((".kml", ".kmz")):
        raise HTTPException(status_code=422, detail="expected a .kml or .kmz file")

    kml_bytes = await file.read()

    try:
        elevation, bbox, kml_lines = parse_contour_kml(kml_bytes)
    except Exception as error:  # noqa: BLE001 -- translating any malformed-upload
        # failure (XML parse errors, bad coordinate values, a corrupted
        # KMZ zip, etc.) into a clean 422 rather than a 500, since this is
        # a user-uploaded file whose failure modes we don't fully control.
        raise HTTPException(status_code=422, detail=f"could not parse contour KML: {error}")

    result = analyze_catchment(elevation, bbox)

    # No "village" for an uploaded survey to hang a rainfall/land lookup off
    # -- use the bbox's own centroid, same idea as reverse-geocoding a click.
    centroid_lat = (bbox.min_lat + bbox.max_lat) / 2
    centroid_lon = (bbox.min_lon + bbox.max_lon) / 2
    recommendation_fields = compute_recommendation_fields(
        centroid_lat, centroid_lon, bbox, result.catchment_area_m2, result.achievable_volume_m3_by_depth
    )

    return CatchmentAnalysisOut(
        **catchment_fields(result).model_dump(),
        **recommendation_fields.model_dump(),
        source_bbox=BoundingBoxOut(
            min_lon=bbox.min_lon, min_lat=bbox.min_lat, max_lon=bbox.max_lon, max_lat=bbox.max_lat
        ),
        grid_resolution=DEFAULT_GRID_SIZE,
        min_elevation=float(elevation.min()),
        max_elevation=float(elevation.max()),
        contours=[
            {"elevation": line.elevation, "coordinates": [[lon, lat] for lon, lat in line.points]}
            for line in kml_lines
        ],
    )
```

(This drops the now-unused `from app.domain.terrain import generate_contours` import — the KML flow no longer re-traces contours, it displays the parsed lines directly. The live-DEM flow in `api/villages.py` is untouched and keeps using `generate_contours` exactly as before.)

- [ ] **Step 6: Run the full backend test suite**

Run: `pytest -q`
Expected: PASS — every test in the suite.

- [ ] **Step 7: Commit**

```bash
git add backend/app/infrastructure/kml_parser.py backend/app/api/analyze_contour.py backend/tests/test_kml_parser.py
git commit -m "Support KMZ uploads and display original KML contour precision"
```

---

### Task 5: Live verification

**Files:** none (verification only)

**Interfaces:** none — this task exercises the whole change set end to end against the real backend.

- [ ] **Step 1: Start the backend**

From `backend/` (venv active): `DATABASE_URL=postgresql+psycopg://hydrosage:hydrosage@localhost:5432/hydrosage OBJECT_STORAGE_ENDPOINT=localhost:9000 REDIS_URL=redis://localhost:6379/0 uvicorn app.main:app --port 8000 --reload` (per `docs/PROJECT_STATUS.md`'s host-run instructions; `postgis`/`redis`/`minio` must already be up via `docker compose up -d postgis redis minio`). Alternatively, `docker compose up -d --build api` runs the same code fully containerized.

- [ ] **Step 2: Verify KMZ upload works end to end**

Zip the real sample file into a KMZ and upload it:

```bash
cd /tmp && cp "C:\Users\kunal\OneDrive\Desktop\CSD\HydroSage\docs\private\contours_1m.kml" doc.kml && zip sample.kmz doc.kml
curl -s -X POST http://localhost:8000/analyzeContour -F "file=@sample.kmz" | python -m json.tool
```

Expected: HTTP 200, a full `CatchmentAnalysisOut` response — confirms the zip-unwrap path works against a real file, not just the synthetic one in `test_kml_parser.py`.

- [ ] **Step 3: Compare contour precision against the original .kml upload**

```bash
curl -s -X POST http://localhost:8000/analyzeContour -F "file=@C:\Users\kunal\OneDrive\Desktop\CSD\HydroSage\docs\private\contours_1m.kml" | python -c "import json,sys; d=json.load(sys.stdin); print('lines:', len(d['contours'])); print('points in first line:', len(d['contours'][0]['coordinates']))"
```

Expected: the point counts reflect the KML's own line density, not a smoothed/re-traced grid — visually confirm in the frontend (`npm run dev`, upload the same file) that the displayed contour lines are visibly more detailed than before this change, matching what was seen in the reference repo's frontend.

- [ ] **Step 4: Verify `fits_terrain_capacity` reports sensible values**

From the same `/analyzeContour` response body (Step 2 or 3), inspect `pond_options`:

```bash
curl -s -X POST http://localhost:8000/analyzeContour -F "file=@C:\Users\kunal\OneDrive\Desktop\CSD\HydroSage\docs\private\contours_1m.kml" | python -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d['pond_options'], indent=2))"
```

Expected: each option has both `fits_available_land` and `fits_terrain_capacity` (`true`, `false`, or `null`), not just the former.

- [ ] **Step 5: Verify depression-preferred site selection on the click-map flow**

```bash
curl -s -X POST http://localhost:8000/villages -H "Content-Type: application/json" -d '{"lat": 21.19, "lon": 81.3}' | python -m json.tool
```

Take the returned `id`, then:

```bash
curl -s http://localhost:8000/villages/<id>/elevation | python -c "import json,sys; d=json.load(sys.stdin); print('pond:', d['pond_location']); print('catchment ha:', d['catchment_area_hectares'])"
```

Expected: a plausible catchment area (1–50ha, per the existing target range) — compare the pond location against the elevation grid informally (e.g. plot it, or check it's not implausibly placed) to sanity-check the depression preference didn't regress site quality for this well-known reference site (Bhilai/Durg, previously verified at 1.96ha per `docs/PROJECT_STATUS.md`).

- [ ] **Step 6: Confirm no console/log errors and no regressions**

Check the `uvicorn` server logs from Steps 2–5 for unexpected tracebacks or warnings beyond the existing, expected ones (e.g. Overpass-unreachable warnings, which are pre-existing and unrelated to this change).

Run the full backend test suite one final time: `pytest -q`
Expected: PASS.

- [ ] **Step 7: Report and stop the server**

Summarize what was verified. Stop the `uvicorn` process (or `docker compose down api` if run containerized).

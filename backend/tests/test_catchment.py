import numpy as np
import pytest

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
from app.infrastructure.elevation_client import BoundingBox


# ---- _sample_candidates: pure logic over a synthetic accumulation array ----


def test_sample_candidates_snaps_to_the_true_local_maximum():
    acc = np.zeros((30, 30))
    acc[14, 16] = 500.0  # off the coarse grid's exact sample points

    candidates = _sample_candidates(acc, margin_rows=2, margin_cols=2)

    assert any(c.row == 14 and c.col == 16 and c.accumulation == 500.0 for c in candidates)


def test_sample_candidates_are_sorted_by_accumulation_descending():
    acc = np.random.default_rng(seed=1).random((40, 40)) * 100

    candidates = _sample_candidates(acc, margin_rows=2, margin_cols=2)

    values = [c.accumulation for c in candidates]
    assert values == sorted(values, reverse=True)


def test_sample_candidates_respects_the_margin():
    acc = np.zeros((30, 30))
    acc[0, 0] = 999.0  # right on the edge -- must be excluded by the margin
    acc[15, 15] = 5.0

    candidates = _sample_candidates(acc, margin_rows=3, margin_cols=3)

    assert all(c.row >= 3 and c.col >= 3 for c in candidates)
    assert not any(c.accumulation == 999.0 for c in candidates)


def test_sample_candidates_has_no_duplicate_positions():
    acc = np.random.default_rng(seed=2).random((25, 25))
    candidates = _sample_candidates(acc, margin_rows=2, margin_cols=2)
    positions = [(c.row, c.col) for c in candidates]
    assert len(positions) == len(set(positions))


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


def test_find_depressions_excludes_cells_outside_a_valid_mask():
    elevation = np.full((20, 20), 100.0)
    elevation[5, 5] = 10.0  # a real depression, inside the valid (genuinely-surveyed) region
    elevation[15, 15] = 10.0  # an identical dip, but outside the valid region -- e.g.
    # a KML interpolation artifact (nearest-neighbor fill outside the survey's convex hull)
    valid_mask = np.ones((20, 20), dtype=bool)
    valid_mask[10:, 10:] = False

    depressions = _find_depressions(elevation, margin_rows=2, margin_cols=2, valid_mask=valid_mask)

    assert depressions[5, 5]
    assert not depressions[15, 15]


def test_find_depressions_no_valid_mask_matches_a_valid_mask_of_none():
    elevation = np.full((20, 20), 100.0)
    elevation[10, 10] = 50.0

    without_mask = _find_depressions(elevation, margin_rows=2, margin_cols=2)
    with_none_mask = _find_depressions(elevation, margin_rows=2, margin_cols=2, valid_mask=None)

    assert np.array_equal(without_mask, with_none_mask)


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


# ---- _select_pond_site: pure selection logic, catchment-area lookup faked ----


def test_select_pond_site_picks_the_first_candidate_within_the_target_range():
    candidates = [
        _Candidate(row=0, col=0, accumulation=100.0),  # too big
        _Candidate(row=1, col=1, accumulation=50.0),  # within range
        _Candidate(row=2, col=2, accumulation=10.0),  # also within range, but ranked lower
    ]
    areas = {
        (0, 0): (None, MAX_CATCHMENT_AREA_M2 * 10),
        (1, 1): (None, (MIN_CATCHMENT_AREA_M2 + MAX_CATCHMENT_AREA_M2) / 2),
        (2, 2): (None, (MIN_CATCHMENT_AREA_M2 + MAX_CATCHMENT_AREA_M2) / 2),
    }

    chosen, _mask, area = _select_pond_site(candidates, lambda c: areas[(c.row, c.col)])

    assert chosen.row == 1 and chosen.col == 1
    assert area == areas[(1, 1)][1]


def test_select_pond_site_falls_back_to_the_closest_candidate_when_none_fit():
    candidates = [
        _Candidate(row=0, col=0, accumulation=100.0),  # way too big
        _Candidate(row=1, col=1, accumulation=50.0),  # just barely too big -- closest to range
        _Candidate(row=2, col=2, accumulation=10.0),  # way too small
    ]
    areas = {
        (0, 0): (None, MAX_CATCHMENT_AREA_M2 * 100),
        (1, 1): (None, MAX_CATCHMENT_AREA_M2 * 1.01),
        (2, 2): (None, MIN_CATCHMENT_AREA_M2 * 0.01),
    }

    chosen, _mask, area = _select_pond_site(candidates, lambda c: areas[(c.row, c.col)])

    assert chosen.row == 1 and chosen.col == 1


def test_select_pond_site_raises_on_an_empty_candidate_list():
    with pytest.raises(ValueError):
        _select_pond_site([], lambda c: (None, 0.0))


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


# ---- analyze_catchment: real pysheds D8 pipeline on synthetic terrain ----


def _bbox_km(size_km: float) -> BoundingBox:
    deg = size_km / 111.32  # rough degrees-per-km at low latitude
    return BoundingBox(min_lon=74.0, min_lat=19.0, max_lon=74.0 + deg, max_lat=19.0 + deg)


def test_analyze_catchment_returns_a_realistically_sized_pond_catchment():
    # A single broad basin sloping toward one corner -- the kind of terrain
    # that, under the old "global highest accumulation" approach, would
    # claim a large fraction of the whole analyzed area as one catchment.
    size = 200
    y, x = np.mgrid[0:size, 0:size]
    elevation = (x + y).astype(np.float64)  # slopes down toward (0, 0)
    bbox = _bbox_km(6.0)  # roughly the click-map flow's real analysis extent

    result = analyze_catchment(elevation, bbox)

    assert MIN_CATCHMENT_AREA_M2 <= result.catchment_area_m2 <= MAX_CATCHMENT_AREA_M2
    assert bbox.min_lon <= result.pond_lon <= bbox.max_lon
    assert bbox.min_lat <= result.pond_lat <= bbox.max_lat


def test_analyze_catchment_still_returns_a_boundary_and_positive_area():
    size = 150
    y, x = np.mgrid[0:size, 0:size]
    center = size / 2
    elevation = 100 - np.sqrt((x - center) ** 2 + (y - center) ** 2)
    bbox = _bbox_km(4.0)

    result = analyze_catchment(elevation, bbox)

    assert result.catchment_area_m2 > 0
    assert result.catchment_cell_count > 0
    assert len(result.catchment_boundary) >= 4


def _radial_basin(size: int = 120) -> np.ndarray:
    """Elevation rising with distance from the centre -- a literal bowl, so
    water collects at the middle. Terrain that unambiguously can hold a
    pond, which makes it a clean test of whether the analysis finds one."""
    y, x = np.mgrid[0:size, 0:size]
    centre = size / 2
    return np.sqrt((x - centre) ** 2 + (y - centre) ** 2).astype(np.float64)


def test_analyze_catchment_pond_site_lies_inside_its_own_catchment():
    # The recommended pond has to sit inside the catchment drawn for it --
    # otherwise the site and the boundary describe different places, and
    # anything computed at the site against that mask (the flood-fill's
    # achievable volume) is meaningless.
    from shapely.geometry import Point, Polygon

    result = analyze_catchment(_radial_basin(), _bbox_km(3.0))

    boundary = Polygon(result.catchment_boundary)
    site = Point(result.pond_lon, result.pond_lat)
    assert boundary.contains(site) or boundary.touches(site)


def test_analyze_catchment_finds_real_storage_in_a_basin():
    # A bowl-shaped basin can obviously hold water; reporting zero
    # achievable volume at every depth means the flood-fill never found the
    # site inside its own catchment.
    result = analyze_catchment(_radial_basin(), _bbox_km(3.0))

    assert any(volume > 0 for volume in result.achievable_volume_m3_by_depth.values())


def test_analyze_catchment_no_valid_mask_matches_an_all_true_valid_mask():
    # valid_mask=None (the default) must behave identically to a valid_mask
    # that excludes nothing -- proves the new parameter is a genuine no-op
    # when every cell is real, surveyed terrain.
    size = 200
    y, x = np.mgrid[0:size, 0:size]
    elevation = (x + y).astype(np.float64)
    bbox = _bbox_km(6.0)

    result_default = analyze_catchment(elevation, bbox)
    result_all_true = analyze_catchment(elevation, bbox, valid_mask=np.ones_like(elevation, dtype=bool))

    assert result_default.pond_lat == result_all_true.pond_lat
    assert result_default.pond_lon == result_all_true.pond_lon
    assert result_default.catchment_area_m2 == result_all_true.catchment_area_m2

import numpy as np
import pytest

from app.domain.catchment import (
    MAX_CATCHMENT_AREA_M2,
    MIN_CATCHMENT_AREA_M2,
    _Candidate,
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

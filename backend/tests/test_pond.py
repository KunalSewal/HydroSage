import pytest

from app.domain.pond import CANDIDATE_DEPTHS_M, recommend_pond_dimensions


def test_recommend_pond_dimensions_back_solves_area_from_volume_and_depth():
    # 6000 m^3 target at 3m depth -> 2000 m^2 surface area, ~44.7m square side
    recommendation = recommend_pond_dimensions(target_storage_m3=6000, candidate_depths_m=(3.0,))

    assert recommendation.target_storage_m3 == 6000
    option = recommendation.options[0]
    assert option.depth_m == 3.0
    assert option.surface_area_m2 == pytest.approx(2000)
    assert option.side_length_m == pytest.approx(2000**0.5)


def test_recommend_pond_dimensions_returns_one_option_per_candidate_depth():
    recommendation = recommend_pond_dimensions(target_storage_m3=1000, candidate_depths_m=(1.0, 2.0, 5.0))
    assert [o.depth_m for o in recommendation.options] == [1.0, 2.0, 5.0]


def test_recommend_pond_dimensions_deeper_pond_needs_less_surface_area():
    recommendation = recommend_pond_dimensions(target_storage_m3=6000, candidate_depths_m=(2.0, 4.0))
    shallow, deep = recommendation.options
    assert deep.surface_area_m2 < shallow.surface_area_m2
    assert deep.surface_area_m2 == pytest.approx(shallow.surface_area_m2 / 2)


def test_recommend_pond_dimensions_uses_documented_default_depths():
    recommendation = recommend_pond_dimensions(target_storage_m3=1000)
    assert [o.depth_m for o in recommendation.options] == list(CANDIDATE_DEPTHS_M)


def test_recommend_pond_dimensions_zero_storage_gives_zero_area():
    recommendation = recommend_pond_dimensions(target_storage_m3=0, candidate_depths_m=(3.0,))
    assert recommendation.options[0].surface_area_m2 == 0
    assert recommendation.options[0].side_length_m == 0


def test_recommend_pond_dimensions_rejects_negative_storage():
    with pytest.raises(ValueError, match="storage"):
        recommend_pond_dimensions(target_storage_m3=-1)


def test_recommend_pond_dimensions_rejects_a_non_positive_depth():
    with pytest.raises(ValueError, match="depth"):
        recommend_pond_dimensions(target_storage_m3=1000, candidate_depths_m=(0.0,))


def test_recommend_pond_dimensions_rejects_an_empty_depth_list():
    with pytest.raises(ValueError, match="depth"):
        recommend_pond_dimensions(target_storage_m3=1000, candidate_depths_m=())

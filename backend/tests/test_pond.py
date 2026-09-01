import pytest

from app.domain.pond import CANDIDATE_DEPTHS_M, recommend_pond_dimensions, size_pond_from_terrain_capacity


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

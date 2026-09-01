import pytest

from app.domain.pond import CANDIDATE_DEPTHS_M, recommend_pond_dimensions, size_pond_options


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

import pytest

from app.domain.runoff import DEFAULT_RUNOFF_COEFFICIENT, estimate_annual_runoff_volume


def test_estimate_annual_runoff_volume_uses_rainfall_times_area_times_coefficient():
    # 1000mm = 1m of rain, over 10,000 m^2 (1 hectare), at coefficient 0.5
    # -> 1m * 10,000 m^2 * 0.5 = 5,000 m^3
    result = estimate_annual_runoff_volume(
        average_annual_rainfall_mm=1000, catchment_area_m2=10_000, runoff_coefficient=0.5
    )
    assert result.runoff_volume_m3 == pytest.approx(5_000)
    assert result.runoff_coefficient == 0.5
    assert result.method == "runoff_coefficient"


def test_estimate_annual_runoff_volume_defaults_to_the_documented_coefficient():
    result = estimate_annual_runoff_volume(average_annual_rainfall_mm=1000, catchment_area_m2=10_000)
    assert result.runoff_coefficient == DEFAULT_RUNOFF_COEFFICIENT
    assert result.runoff_volume_m3 == pytest.approx(1000 / 1000 * 10_000 * DEFAULT_RUNOFF_COEFFICIENT)


def test_estimate_annual_runoff_volume_matches_a_real_bhilai_scale_example():
    # Real figures from this session's live verification: ~1436.4mm annual
    # rainfall, ~8,137,923 m^2 (813.8 ha) catchment area for Bhilai/Durg.
    result = estimate_annual_runoff_volume(
        average_annual_rainfall_mm=1436.4, catchment_area_m2=8_137_923, runoff_coefficient=0.25
    )
    assert result.runoff_volume_m3 == pytest.approx(2_922_973, rel=0.001)


@pytest.mark.parametrize("zero_input", [{"average_annual_rainfall_mm": 0}, {"catchment_area_m2": 0}])
def test_estimate_annual_runoff_volume_is_zero_when_rainfall_or_area_is_zero(zero_input):
    args = {"average_annual_rainfall_mm": 1000, "catchment_area_m2": 10_000, **zero_input}
    result = estimate_annual_runoff_volume(**args)
    assert result.runoff_volume_m3 == 0


def test_estimate_annual_runoff_volume_rejects_negative_rainfall():
    with pytest.raises(ValueError, match="rainfall"):
        estimate_annual_runoff_volume(average_annual_rainfall_mm=-1, catchment_area_m2=10_000)


def test_estimate_annual_runoff_volume_rejects_negative_area():
    with pytest.raises(ValueError, match="area"):
        estimate_annual_runoff_volume(average_annual_rainfall_mm=1000, catchment_area_m2=-1)


@pytest.mark.parametrize("bad_coefficient", [-0.1, 1.1])
def test_estimate_annual_runoff_volume_rejects_a_coefficient_outside_zero_to_one(bad_coefficient):
    with pytest.raises(ValueError, match="coefficient"):
        estimate_annual_runoff_volume(
            average_annual_rainfall_mm=1000, catchment_area_m2=10_000, runoff_coefficient=bad_coefficient
        )

import pytest

from app.domain.rainfall import summarize_rainfall
from app.infrastructure.rainfall_client import DailyRainfall


def _daily(year: int, month: int, day: int, mm: float) -> DailyRainfall:
    return DailyRainfall(date=f"{year:04d}-{month:02d}-{day:02d}", precipitation_mm=mm)


def test_summarize_rainfall_averages_a_single_year():
    daily = [_daily(2023, 1, 1, 10.0), _daily(2023, 1, 2, 20.0), _daily(2023, 7, 1, 100.0)]

    summary = summarize_rainfall(daily)

    assert summary.average_annual_mm == pytest.approx(130.0)
    assert summary.monthly_average_mm[0] == pytest.approx(30.0)  # January
    assert summary.monthly_average_mm[6] == pytest.approx(100.0)  # July
    assert summary.monthly_average_mm[1] == pytest.approx(0.0)  # February, no data


def test_summarize_rainfall_averages_across_multiple_full_years():
    daily = [
        _daily(2022, 1, 15, 10.0),
        _daily(2023, 1, 15, 30.0),
        _daily(2022, 7, 1, 50.0),
        _daily(2023, 7, 1, 150.0),
    ]

    summary = summarize_rainfall(daily)

    assert summary.monthly_average_mm[0] == pytest.approx(20.0)  # (10 + 30) / 2 years
    assert summary.monthly_average_mm[6] == pytest.approx(100.0)  # (50 + 150) / 2 years
    assert summary.average_annual_mm == pytest.approx(120.0)


def test_summarize_rainfall_sets_the_period_from_the_first_and_last_day():
    daily = [_daily(2020, 1, 1, 0.0), _daily(2022, 12, 31, 0.0)]

    summary = summarize_rainfall(daily)

    assert summary.period_start == "2020-01-01"
    assert summary.period_end == "2022-12-31"


def test_summarize_rainfall_treats_missing_values_as_zero():
    daily = [DailyRainfall(date="2023-01-01", precipitation_mm=0.0)]
    summary = summarize_rainfall(daily)
    assert summary.average_annual_mm == pytest.approx(0.0)


def test_summarize_rainfall_rejects_an_empty_series():
    with pytest.raises(ValueError):
        summarize_rainfall([])

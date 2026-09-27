"""Aggregates daily rainfall into the monthly/annual statistics the rest of
the app consumes (runoff estimation, eventual display). Pure function: no
I/O, no FastAPI/DB imports -- testable in isolation, per docs/ARCHITECTURE.md.
"""

from collections import defaultdict
from dataclasses import dataclass

from app.infrastructure.rainfall_client import DailyRainfall


@dataclass(frozen=True)
class RainfallSummary:
    period_start: str
    period_end: str
    average_annual_mm: float
    monthly_average_mm: list[float]  # 12 values, Jan..Dec


def summarize_rainfall(daily: list[DailyRainfall]) -> RainfallSummary:
    if not daily:
        raise ValueError("no rainfall data to summarize")

    years = {int(d.date[:4]) for d in daily}
    num_years = len(years)

    monthly_totals: dict[int, float] = defaultdict(float)
    for d in daily:
        month = int(d.date[5:7])
        monthly_totals[month] += d.precipitation_mm

    monthly_average_mm = [monthly_totals[month] / num_years for month in range(1, 13)]

    return RainfallSummary(
        period_start=daily[0].date,
        period_end=daily[-1].date,
        average_annual_mm=sum(monthly_average_mm),
        monthly_average_mm=monthly_average_mm,
    )


# Mean days per month, with February averaged over leap years, so a
# climatology's mm/day rates convert to the same mean-month totals that
# summarize_rainfall produces from daily records.
_MEAN_DAYS_IN_MONTH = [31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def summarize_climatology(
    monthly_mm_per_day: list[float], period_start: str, period_end: str
) -> RainfallSummary:
    """The same summary as summarize_rainfall, from long-term monthly mean
    rates (mm/day) instead of daily records -- the shape NASA POWER's
    climatology endpoint returns."""
    if len(monthly_mm_per_day) != 12:
        raise ValueError("expected 12 monthly values, Jan..Dec")

    monthly_average_mm = [rate * days for rate, days in zip(monthly_mm_per_day, _MEAN_DAYS_IN_MONTH)]
    return RainfallSummary(
        period_start=period_start,
        period_end=period_end,
        average_annual_mm=sum(monthly_average_mm),
        monthly_average_mm=monthly_average_mm,
    )

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

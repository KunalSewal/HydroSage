"""Client for Open-Meteo's historical weather archive (ERA5 reanalysis).
Free, no API key, global coverage -- chosen over NASA POWER (also free,
also no key, also named in the project brief) for its finer resolution:
ERA5 is ~9-25km, MERRA-2 (what NASA POWER serves) is ~50km.
"""

from dataclasses import dataclass
from datetime import date

import httpx

from app.core.config import get_settings


@dataclass(frozen=True)
class DailyRainfall:
    date: str  # ISO date, e.g. "2023-07-04"
    precipitation_mm: float


class RainfallClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        settings = get_settings()
        self._client = client or httpx.Client(base_url=settings.open_meteo_base_url, timeout=30.0)

    def get_daily_rainfall(self, lat: float, lon: float, start: date, end: date) -> list[DailyRainfall]:
        response = self._client.get(
            "/v1/archive",
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "daily": "precipitation_sum",
                "timezone": "auto",
            },
        )
        response.raise_for_status()
        body = response.json()
        days = body["daily"]["time"]
        values = body["daily"]["precipitation_sum"]
        # A day with no reading comes back as null rather than 0 -- treat it
        # as no rainfall recorded rather than propagating None downstream.
        return [DailyRainfall(date=d, precipitation_mm=v or 0.0) for d, v in zip(days, values)]

    def close(self) -> None:
        self._client.close()

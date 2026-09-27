"""Client for NASA POWER's climatology API (MERRA-2, ~50 km).

The fallback rainfall source, not the primary: Open-Meteo's ERA5 archive
(rainfall_client.py) has finer resolution, but its free tier has a daily
request limit, and hitting it left the app with no water-volume estimate
at all (measured 2026-09-27: "Daily API request limit exceeded"). POWER
needs no key, answers one light request with a pre-computed 20-year
monthly mean, and is named in the project brief. See docs/DECISIONS.md
D-014.
"""

import httpx

from app.core.config import get_settings

MONTH_KEYS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
FILL_VALUE = -999.0

# The fixed period POWER's climatology endpoint averages over, stated in
# every response header ("January 2001 - December 2020").
CLIMATOLOGY_PERIOD_START = "2001-01-01"
CLIMATOLOGY_PERIOD_END = "2020-12-31"


POWER_TIMEOUT_S = 10.0


class NasaPowerClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        settings = get_settings()
        # Shorter than the shared rainfall timeout: a healthy POWER answer
        # takes under a second, and the caller retries once (see
        # services/rainfall_lookup.py), so waiting 30 s on a stalled request
        # only delays that retry.
        self._client = client or httpx.Client(base_url=settings.nasa_power_base_url, timeout=POWER_TIMEOUT_S)

    def get_monthly_precipitation_rates(self, lat: float, lon: float) -> list[float]:
        """Mean precipitation for each month, Jan..Dec, in mm/day."""
        response = self._client.get(
            "/api/temporal/climatology/point",
            params={
                "parameters": "PRECTOTCORR",
                "community": "AG",
                "latitude": lat,
                "longitude": lon,
                "format": "JSON",
            },
        )
        response.raise_for_status()
        by_month = response.json()["properties"]["parameter"]["PRECTOTCORR"]
        rates = [float(by_month[key]) for key in MONTH_KEYS]
        if any(rate == FILL_VALUE for rate in rates):
            raise ValueError("NASA POWER returned missing precipitation data for this location")
        return rates

    def close(self) -> None:
        self._client.close()

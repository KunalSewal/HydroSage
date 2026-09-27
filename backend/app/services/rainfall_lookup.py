"""Average annual rainfall for a location: Open-Meteo first, NASA POWER if
that fails, remembered in process for a few hours either way.

Rainfall is the input the expected water volume depends on, so a single
provider's outage or quota must not remove the volume from the result.
Open-Meteo's free tier enforces a daily request limit per IP, which a
demo, a load test or several graders can exhaust. See docs/DECISIONS.md
D-014.

The cache is per process and deliberately simple: a location's long-term
rainfall doesn't change within hours, each API instance warms its own
copy after one lookup, and nothing is lost if it's empty.
"""

import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import date

from app.domain.rainfall import RainfallSummary, summarize_climatology, summarize_rainfall
from app.infrastructure.nasa_power_client import (
    CLIMATOLOGY_PERIOD_END,
    CLIMATOLOGY_PERIOD_START,
    NasaPowerClient,
)
from app.infrastructure.rainfall_client import RainfallClient

logger = logging.getLogger(__name__)

RAINFALL_HISTORY_YEARS = 10
CACHE_TTL_SECONDS = 6 * 3600
CACHE_MAX_ENTRIES = 1024

_cache: OrderedDict[tuple[float, float], tuple[float, RainfallSummary, str]] = OrderedDict()
_cache_lock = threading.Lock()  # sync endpoints run in a thread pool


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _cache_key(lat: float, lon: float) -> tuple[float, float]:
    # ~11 m. Only dedupes repeat requests for the same place; it never
    # substitutes a neighbouring location's rainfall.
    return (round(lat, 4), round(lon, 4))


def _from_open_meteo(client: RainfallClient, lat: float, lon: float) -> RainfallSummary:
    end_year = date.today().year - 1
    start = date(end_year - RAINFALL_HISTORY_YEARS + 1, 1, 1)
    end = date(end_year, 12, 31)
    return summarize_rainfall(client.get_daily_rainfall(lat, lon, start, end))


def _from_nasa_power(client: NasaPowerClient, lat: float, lon: float) -> RainfallSummary:
    rates = client.get_monthly_precipitation_rates(lat, lon)
    return summarize_climatology(rates, CLIMATOLOGY_PERIOD_START, CLIMATOLOGY_PERIOD_END)


def get_rainfall_summary(
    lat: float,
    lon: float,
    primary: Callable[[], RainfallClient] = RainfallClient,
    fallback: Callable[[], NasaPowerClient] = NasaPowerClient,
) -> tuple[RainfallSummary, str] | None:
    """(summary, source name), or None if every source failed."""
    key = _cache_key(lat, lon)
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
            _cache.move_to_end(key)
            return cached[1], cached[2]

    # POWER, as the last resort, gets a second attempt: it occasionally
    # stalls on a single request and answers the next one in under a second.
    # Open-Meteo's usual failure is a quota refusal, which retrying can't fix.
    sources = [
        ("open-meteo", primary, _from_open_meteo, 1),
        ("nasa-power", fallback, _from_nasa_power, 2),
    ]
    for name, make_client, summarize, attempts in sources:
        summary = None
        for attempt in range(1, attempts + 1):
            client = make_client()
            try:
                summary = summarize(client, lat, lon)
                break
            except Exception:  # noqa: BLE001 -- any provider failure means "retry, or try the next one"
                logger.warning("rainfall source %s failed (attempt %d/%d)", name, attempt, attempts, exc_info=True)
            finally:
                client.close()
        if summary is None:
            continue

        with _cache_lock:
            _cache[key] = (time.monotonic(), summary, name)
            _cache.move_to_end(key)
            while len(_cache) > CACHE_MAX_ENTRIES:
                _cache.popitem(last=False)
        return summary, name

    return None

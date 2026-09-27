import httpx
import pytest

from app.infrastructure.rainfall_client import DailyRainfall
from app.services import rainfall_lookup
from app.services.rainfall_lookup import get_rainfall_summary


class _OpenMeteo:
    calls = 0

    def __init__(self, fail: bool = False):
        self.fail = fail

    def get_daily_rainfall(self, lat, lon, start, end):
        type(self).calls += 1
        if self.fail:
            request = httpx.Request("GET", "https://x.test")
            raise httpx.HTTPStatusError("429", request=request, response=httpx.Response(429, request=request))
        return [DailyRainfall(date="2020-07-01", precipitation_mm=1000.0)]

    def close(self):
        pass


class _Power:
    def __init__(self, fail: bool = False):
        self.fail = fail

    def get_monthly_precipitation_rates(self, lat, lon):
        if self.fail:
            raise httpx.ConnectError("down")
        return [2.0] * 12

    def close(self):
        pass


@pytest.fixture(autouse=True)
def empty_cache():
    rainfall_lookup.clear_cache()
    _OpenMeteo.calls = 0
    yield
    rainfall_lookup.clear_cache()


def test_uses_open_meteo_when_it_answers():
    result = get_rainfall_summary(21.0, 81.0, primary=lambda: _OpenMeteo(), fallback=lambda: _Power())

    summary, source = result
    assert source == "open-meteo"
    assert summary.average_annual_mm == pytest.approx(1000.0)


def test_falls_back_to_nasa_power_when_open_meteo_is_rate_limited():
    result = get_rainfall_summary(21.0, 81.0, primary=lambda: _OpenMeteo(fail=True), fallback=lambda: _Power())

    summary, source = result
    assert source == "nasa-power"
    assert summary.average_annual_mm == pytest.approx(2.0 * 365.25)


def test_returns_none_when_every_source_fails():
    result = get_rainfall_summary(
        21.0, 81.0, primary=lambda: _OpenMeteo(fail=True), fallback=lambda: _Power(fail=True)
    )

    assert result is None


def test_a_repeat_lookup_for_the_same_place_is_served_from_cache():
    for _ in range(3):
        get_rainfall_summary(21.0, 81.0, primary=lambda: _OpenMeteo(), fallback=lambda: _Power())

    assert _OpenMeteo.calls == 1


def test_a_failed_lookup_is_not_cached():
    get_rainfall_summary(21.0, 81.0, primary=lambda: _OpenMeteo(fail=True), fallback=lambda: _Power(fail=True))
    result = get_rainfall_summary(21.0, 81.0, primary=lambda: _OpenMeteo(), fallback=lambda: _Power())

    assert result is not None


def test_retries_nasa_power_once_after_a_transient_failure():
    # POWER occasionally stalls on a single request; as the last resort it
    # gets a second attempt before the volume is given up on.
    attempts = []

    class _FlakyPower(_Power):
        def get_monthly_precipitation_rates(self, lat, lon):
            attempts.append(1)
            if len(attempts) == 1:
                raise httpx.ReadTimeout("stalled")
            return [2.0] * 12

    result = get_rainfall_summary(21.0, 81.0, primary=lambda: _OpenMeteo(fail=True), fallback=lambda: _FlakyPower())

    assert result is not None and result[1] == "nasa-power"
    assert len(attempts) == 2

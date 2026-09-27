import httpx
import pytest

from app.infrastructure.nasa_power_client import NasaPowerClient

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def _power_response(values: list[float]) -> dict:
    data = dict(zip(MONTHS, values))
    data["ANN"] = sum(values) / 12
    return {
        "properties": {"parameter": {"PRECTOTCORR": data}},
        "header": {"range": "20-year Meteorological and Solar Monthly & Annual Climatologies (January 2001 - December 2020)"},
    }


def test_get_monthly_precipitation_rates_returns_jan_to_dec_in_order():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.url.params))
        return httpx.Response(200, json=_power_response([float(i) for i in range(1, 13)]))

    client = NasaPowerClient(client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://x.test"))

    rates = client.get_monthly_precipitation_rates(21.18, 81.27)

    assert rates == [float(i) for i in range(1, 13)]
    assert captured["parameters"] == "PRECTOTCORR"
    assert captured["latitude"] == "21.18"
    assert captured["longitude"] == "81.27"


def test_get_monthly_precipitation_rates_rejects_fill_values():
    # POWER marks missing data with -999 rather than an error status.
    values = [1.0] * 12
    values[6] = -999.0

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_power_response(values))

    client = NasaPowerClient(client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://x.test"))

    with pytest.raises(ValueError, match="missing"):
        client.get_monthly_precipitation_rates(21.18, 81.27)


def test_get_monthly_precipitation_rates_raises_on_an_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = NasaPowerClient(client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://x.test"))

    with pytest.raises(httpx.HTTPStatusError):
        client.get_monthly_precipitation_rates(21.18, 81.27)

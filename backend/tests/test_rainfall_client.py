import os
from datetime import date

import httpx
import pytest

from app.infrastructure.rainfall_client import RainfallClient


def test_get_daily_rainfall_parses_the_response_and_treats_nulls_as_zero():
    captured_params = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_params.update(dict(request.url.params))
        return httpx.Response(
            200,
            json={
                "daily": {
                    "time": ["2023-01-01", "2023-01-02", "2023-01-03"],
                    "precipitation_sum": [0.0, 12.4, None],
                }
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test")
    client = RainfallClient(client=http_client)

    result = client.get_daily_rainfall(21.19, 81.30, date(2023, 1, 1), date(2023, 1, 3))

    assert [d.precipitation_mm for d in result] == [0.0, 12.4, 0.0]
    assert [d.date for d in result] == ["2023-01-01", "2023-01-02", "2023-01-03"]
    assert captured_params["latitude"] == "21.19"
    assert captured_params["longitude"] == "81.3"
    assert captured_params["start_date"] == "2023-01-01"
    assert captured_params["end_date"] == "2023-01-03"


def test_get_daily_rainfall_raises_on_an_error_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"reason": "bad request"})

    http_client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test")
    client = RainfallClient(client=http_client)

    with pytest.raises(httpx.HTTPStatusError):
        client.get_daily_rainfall(21.19, 81.30, date(2023, 1, 1), date(2023, 1, 3))


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="hits the live Open-Meteo archive API; set RUN_INTEGRATION_TESTS=1 to run",
)
def test_get_daily_rainfall_returns_plausible_data_for_bhilai():
    client = RainfallClient()

    result = client.get_daily_rainfall(21.19, 81.30, date(2023, 7, 1), date(2023, 7, 5))

    assert len(result) == 5
    total = sum(d.precipitation_mm for d in result)
    assert total > 0  # monsoon-season Chhattisgarh, some rain expected across 5 days
    client.close()

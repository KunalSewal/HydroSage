import os

import httpx
import pytest

from app.infrastructure.elevation_client import BoundingBox
from app.infrastructure.land_use_client import LandUseClient


def test_get_excluded_features_parses_ways_into_area_and_line_features():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "elements": [
                    {
                        "type": "way",
                        "tags": {"building": "yes"},
                        "geometry": [
                            {"lat": 19.0, "lon": 74.0},
                            {"lat": 19.0, "lon": 74.001},
                            {"lat": 19.001, "lon": 74.001},
                            {"lat": 19.0, "lon": 74.0},
                        ],
                    },
                    {
                        "type": "way",
                        "tags": {"highway": "unclassified"},
                        "geometry": [{"lat": 19.0, "lon": 74.0}, {"lat": 19.001, "lon": 74.001}],
                    },
                    {
                        "type": "way",
                        "tags": {"building": "yes"},
                        # no geometry -- e.g. a way whose nodes weren't resolved -- must be skipped
                    },
                ]
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test")
    client = LandUseClient(client=http_client)

    features = client.get_excluded_features(BoundingBox(min_lon=74.0, min_lat=19.0, max_lon=74.01, max_lat=19.01))

    assert len(features) == 2
    assert features[0].kind == "area"
    assert features[0].coordinates == [(74.0, 19.0), (74.001, 19.0), (74.001, 19.001), (74.0, 19.0)]
    assert features[1].kind == "line"


def test_get_excluded_features_sends_the_bbox_in_the_query():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"elements": []})

    http_client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test")
    client = LandUseClient(client=http_client)

    client.get_excluded_features(BoundingBox(min_lon=74.1, min_lat=19.1, max_lon=74.2, max_lat=19.2))

    assert "19.1" in captured["body"]
    assert "74.1" in captured["body"]
    assert "19.2" in captured["body"]
    assert "74.2" in captured["body"]


def test_get_excluded_features_raises_on_an_error_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(504, text="gateway timeout")

    http_client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test")
    client = LandUseClient(client=http_client)

    with pytest.raises(httpx.HTTPStatusError):
        client.get_excluded_features(BoundingBox(min_lon=74.0, min_lat=19.0, max_lon=74.01, max_lat=19.01))


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="hits the live Overpass API; set RUN_INTEGRATION_TESTS=1 to run",
)
def test_get_excluded_features_returns_real_data_for_bhilai():
    client = LandUseClient()

    features = client.get_excluded_features(
        BoundingBox(min_lon=81.28, min_lat=21.17, max_lon=81.32, max_lat=21.21)
    )

    assert len(features) > 0
    assert any(f.kind == "area" for f in features)
    assert any(f.kind == "line" for f in features)
    client.close()

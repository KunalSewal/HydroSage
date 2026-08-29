import os

import httpx
import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds

from app.infrastructure.elevation_client import BoundingBox, ElevationClient


class _FakeDemCache:
    """In-memory stand-in for DemCache -- lets ElevationClient's own
    cache-hit/cache-miss wiring be tested without a real MinIO instance
    (that's DemCache's own job, covered in test_dem_cache.py)."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], bytes] = {}
        self.get_calls: list[tuple[str, str]] = []
        self.put_calls: list[tuple[str, str]] = []

    def get(self, cache_key: str, demtype: str) -> bytes | None:
        self.get_calls.append((cache_key, demtype))
        return self.store.get((cache_key, demtype))

    def put(self, cache_key: str, demtype: str, raw: bytes) -> None:
        self.put_calls.append((cache_key, demtype))
        self.store[(cache_key, demtype)] = raw


def _fake_geotiff_bytes(bbox: BoundingBox, fill_value: float = 123.0) -> bytes:
    """A small, real, decodable single-band GeoTIFF -- so ElevationClient's
    actual rasterio-decoding path is exercised, not bypassed."""
    width, height = 4, 4
    transform = from_bounds(bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat, width, height)
    data = np.full((height, width), fill_value, dtype=np.float64)
    with MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff", width=width, height=height, count=1, dtype="float64",
            crs="EPSG:4326", transform=transform,
        ) as dataset:
            dataset.write(data, 1)
        return memfile.read()


def test_get_dem_for_bbox_fetches_live_and_populates_the_cache_on_a_miss():
    bbox = BoundingBox(min_lon=74.0, min_lat=19.0, max_lon=74.1, max_lat=19.1)
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, content=_fake_geotiff_bytes(bbox))

    http_client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test")
    cache = _FakeDemCache()
    client = ElevationClient(client=http_client, cache=cache)

    elevation, _covered = client.get_dem_for_bbox(bbox, cache_key="village-1")

    assert call_count == 1
    assert elevation.min() == pytest.approx(123.0)
    assert cache.put_calls == [("village-1", "COP30")]


def test_get_dem_for_bbox_skips_the_network_call_on_a_cache_hit():
    bbox = BoundingBox(min_lon=74.0, min_lat=19.0, max_lon=74.1, max_lat=19.1)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not hit the network on a cache hit")

    http_client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test")
    cache = _FakeDemCache()
    cache.store[("village-1", "COP30")] = _fake_geotiff_bytes(bbox, fill_value=456.0)
    client = ElevationClient(client=http_client, cache=cache)

    elevation, _covered = client.get_dem_for_bbox(bbox, cache_key="village-1")

    assert elevation.min() == pytest.approx(456.0)
    assert cache.put_calls == []  # already cached, nothing new to store


def test_get_dem_for_bbox_without_a_cache_key_never_touches_the_cache():
    bbox = BoundingBox(min_lon=74.0, min_lat=19.0, max_lon=74.1, max_lat=19.1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_fake_geotiff_bytes(bbox))

    http_client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test")
    cache = _FakeDemCache()
    client = ElevationClient(client=http_client, cache=cache)

    client.get_dem_for_bbox(bbox)  # no cache_key -- e.g. a future caller that doesn't want caching

    assert cache.get_calls == []
    assert cache.put_calls == []


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="hits the live OpenTopography API; set RUN_INTEGRATION_TESTS=1 to run",
)
def test_get_dem_for_bbox_returns_plausible_elevation_for_hiware_bazar():
    client = ElevationClient()
    # Hiware Bazar, Maharashtra — see docs/DECISIONS.md D-004. Known range
    # from a prior verified call: 662.8-959.2m for this exact bbox.
    bbox = BoundingBox(min_lon=74.53125, min_lat=19.020577, max_lon=74.663086, max_lat=19.103648)

    elevation, covered = client.get_dem_for_bbox(bbox)

    assert isinstance(elevation, np.ndarray)
    assert elevation.ndim == 2
    assert 600 < elevation.min() < 700
    assert 900 < elevation.max() < 1000
    assert covered.min_lon == pytest.approx(bbox.min_lon, abs=0.01)
    assert covered.max_lat == pytest.approx(bbox.max_lat, abs=0.01)
    client.close()

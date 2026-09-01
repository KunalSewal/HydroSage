import os

import pytest

from app.core.config import get_settings
from app.domain.catchment import CatchmentResult
from app.infrastructure.catchment_cache import CatchmentCache

_RESULT = CatchmentResult(
    pond_lat=21.24,
    pond_lon=81.29,
    catchment_area_m2=19_613.75,
    catchment_cell_count=42,
    flow_accumulation_at_pond=999.0,
    catchment_boundary=[[81.28, 21.24], [81.29, 21.25], [81.28, 21.24]],
    achievable_volume_m3_by_depth={2.0: 5_000.0, 3.0: 6_500.0, 4.0: 7_000.0},
)


class _FakeRedis:
    """In-memory stand-in for redis.Redis -- tests CatchmentCache's own
    logic (serialization, key construction, error handling) without a
    real Redis instance."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, name):
        value = self.store.get(name)
        return value.encode() if value is not None else None

    def set(self, name, value, ex=None):
        self.store[name] = value


class _AlwaysBrokenRedis:
    def get(self, *args, **kwargs):
        raise ConnectionError("redis is not reachable")

    def set(self, *args, **kwargs):
        raise ConnectionError("redis is not reachable")


def test_get_returns_none_on_a_cache_miss():
    cache = CatchmentCache(_FakeRedis())
    assert cache.get("village-1") is None


def test_put_then_get_round_trips_the_same_result():
    fake = _FakeRedis()
    cache = CatchmentCache(fake)

    cache.put("village-1", _RESULT)

    assert cache.get("village-1") == _RESULT


def test_different_villages_do_not_collide():
    fake = _FakeRedis()
    cache = CatchmentCache(fake)
    other = CatchmentResult(
        pond_lat=1.0, pond_lon=2.0, catchment_area_m2=1.0, catchment_cell_count=1,
        flow_accumulation_at_pond=1.0, catchment_boundary=[], achievable_volume_m3_by_depth={},
    )

    cache.put("village-1", _RESULT)
    cache.put("village-2", other)

    assert cache.get("village-1") == _RESULT
    assert cache.get("village-2") == other


def test_get_degrades_to_a_cache_miss_when_redis_is_unreachable():
    cache = CatchmentCache(_AlwaysBrokenRedis())
    assert cache.get("village-1") is None


def test_put_degrades_silently_when_redis_is_unreachable():
    cache = CatchmentCache(_AlwaysBrokenRedis())
    cache.put("village-1", _RESULT)  # must not raise


def test_get_degrades_to_a_cache_miss_on_a_corrupted_entry():
    fake = _FakeRedis()
    fake.store["catchment:village-1"] = "not valid json"
    cache = CatchmentCache(fake)
    assert cache.get("village-1") is None


def test_get_or_compute_calls_compute_only_on_a_miss():
    fake = _FakeRedis()
    cache = CatchmentCache(fake)
    calls = []

    def compute():
        calls.append(1)
        return _RESULT

    first = cache.get_or_compute("village-1", compute)
    second = cache.get_or_compute("village-1", compute)

    assert first == _RESULT
    assert second == _RESULT
    assert len(calls) == 1  # only computed once -- the second call hit the cache


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="needs a live Redis instance; set RUN_INTEGRATION_TESTS=1 to run",
)
def test_round_trips_through_a_real_redis_instance():
    cache = CatchmentCache.from_settings(get_settings())

    cache.put("test-village-real-redis", _RESULT)

    assert cache.get("test-village-real-redis") == _RESULT
    assert cache.get("a-village-never-written") is None

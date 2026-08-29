import os

import pytest
from minio.error import S3Error

from app.core.config import get_settings
from app.infrastructure.dem_cache import DemCache


class _FakeMinioResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self.closed = False
        self.released = False

    def read(self) -> bytes:
        return self._data

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


def _s3_error(code: str) -> S3Error:
    return S3Error(None, code, "message", "resource", "request_id", "host_id")


class _FakeMinioClient:
    """In-memory stand-in for minio.Minio, so DemCache's own logic (key
    construction, cache-miss/error handling) is tested without needing a
    real MinIO server."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.bucket_exists_calls = 0
        self.make_bucket_calls = 0
        self._bucket_created = False

    def get_object(self, bucket_name, object_name):
        key = (bucket_name, object_name)
        if key not in self.objects:
            raise _s3_error("NoSuchKey")
        return _FakeMinioResponse(self.objects[key])

    def put_object(self, bucket_name, object_name, data, length, content_type=None):
        self.objects[(bucket_name, object_name)] = data.read()

    def bucket_exists(self, bucket_name):
        self.bucket_exists_calls += 1
        return self._bucket_created

    def make_bucket(self, bucket_name):
        self.make_bucket_calls += 1
        self._bucket_created = True


class _AlwaysBrokenMinioClient:
    """Simulates MinIO being completely unreachable (connection refused,
    DNS failure, etc.) -- not an S3Error, a lower-level exception."""

    def get_object(self, *args, **kwargs):
        raise ConnectionError("MinIO is not reachable")

    def put_object(self, *args, **kwargs):
        raise ConnectionError("MinIO is not reachable")

    def bucket_exists(self, *args, **kwargs):
        raise ConnectionError("MinIO is not reachable")

    def make_bucket(self, *args, **kwargs):
        raise ConnectionError("MinIO is not reachable")


def test_get_returns_none_on_a_cache_miss():
    cache = DemCache(_FakeMinioClient(), bucket="test-bucket")
    assert cache.get("village-1", "COP30") is None


def test_put_then_get_round_trips_the_same_bytes():
    fake_client = _FakeMinioClient()
    cache = DemCache(fake_client, bucket="test-bucket")

    cache.put("village-1", "COP30", b"fake geotiff bytes")

    assert cache.get("village-1", "COP30") == b"fake geotiff bytes"


def test_put_creates_the_bucket_lazily_on_first_write():
    fake_client = _FakeMinioClient()
    cache = DemCache(fake_client, bucket="test-bucket")

    assert fake_client.make_bucket_calls == 0  # not created just by constructing DemCache
    cache.put("village-1", "COP30", b"data")
    assert fake_client.make_bucket_calls == 1


def test_different_cache_keys_and_demtypes_do_not_collide():
    fake_client = _FakeMinioClient()
    cache = DemCache(fake_client, bucket="test-bucket")

    cache.put("village-1", "COP30", b"village 1 data")
    cache.put("village-2", "COP30", b"village 2 data")
    cache.put("village-1", "SRTMGL1", b"village 1, different demtype")

    assert cache.get("village-1", "COP30") == b"village 1 data"
    assert cache.get("village-2", "COP30") == b"village 2 data"
    assert cache.get("village-1", "SRTMGL1") == b"village 1, different demtype"


def test_get_degrades_to_a_cache_miss_when_minio_is_unreachable():
    cache = DemCache(_AlwaysBrokenMinioClient(), bucket="test-bucket")
    assert cache.get("village-1", "COP30") is None  # falls back, doesn't raise


def test_put_degrades_silently_when_minio_is_unreachable():
    cache = DemCache(_AlwaysBrokenMinioClient(), bucket="test-bucket")
    cache.put("village-1", "COP30", b"data")  # must not raise -- caching is best-effort


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="needs a live MinIO instance; set RUN_INTEGRATION_TESTS=1 to run",
)
def test_round_trips_through_a_real_minio_instance():
    cache = DemCache.from_settings(get_settings())

    cache.put("test-village-real-minio", "COP30", b"real minio round trip")

    assert cache.get("test-village-real-minio", "COP30") == b"real minio round trip"
    assert cache.get("test-village-real-minio", "a-demtype-never-written") is None

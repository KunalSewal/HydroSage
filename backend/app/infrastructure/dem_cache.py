"""MinIO-backed cache for raw DEM GeoTIFF bytes, keyed by an already-stable
identifier (a village id) plus the DEM product type. Exists so a given
site's terrain is only ever fetched from OpenTopography once -- its free
tier is 50 calls/day -- no matter how many times that site gets re-analyzed
or how many people look at it. See docs/DECISIONS.md D-005.

Caching is an optimization, not a correctness requirement: every failure
mode here (MinIO down, bucket missing, a corrupted object) degrades to "no
cache" rather than raising, so a cache outage never breaks the live DEM
fetch it's sitting in front of.
"""

import hashlib
import logging
import os
from io import BytesIO
from pathlib import Path

import urllib3
from minio import Minio

from app.core.config import Settings

logger = logging.getLogger(__name__)

# minio's default HTTP client retries a refused connection with backoff for
# over a minute. Measured: 70 s added to every request while MinIO was down,
# against a 12 s live DEM fetch it was meant to save. A cache that can't
# answer in a couple of seconds should count as a miss.
_CONNECT_TIMEOUT_S = 2.0
_READ_TIMEOUT_S = 10.0


class DemCache:
    def __init__(self, client: Minio, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    @classmethod
    def from_settings(cls, settings: Settings) -> "DemCache | DiskDemCache":
        if settings.dem_cache_dir:
            return DiskDemCache(Path(settings.dem_cache_dir))
        client = Minio(
            settings.object_storage_endpoint,
            access_key=settings.object_storage_access_key,
            secret_key=settings.object_storage_secret_key,
            secure=settings.object_storage_secure,
            http_client=urllib3.PoolManager(
                timeout=urllib3.Timeout(connect=_CONNECT_TIMEOUT_S, read=_READ_TIMEOUT_S),
                retries=urllib3.Retry(total=0),
            ),
        )
        return cls(client, settings.object_storage_bucket)

    def get(self, cache_key: str, demtype: str) -> bytes | None:
        try:
            response = self._client.get_object(self._bucket, self._object_name(cache_key, demtype))
        except Exception:  # noqa: BLE001 -- any failure (missing key, missing bucket, MinIO
            # unreachable) is treated as a cache miss so the caller falls back to a live fetch.
            return None
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def put(self, cache_key: str, demtype: str, raw: bytes) -> None:
        try:
            self._ensure_bucket()
            self._client.put_object(
                self._bucket,
                self._object_name(cache_key, demtype),
                data=BytesIO(raw),
                length=len(raw),
                content_type="image/tiff",
            )
        except Exception:  # noqa: BLE001 -- a failed write must not fail the request that
            # triggered it; the next request just fetches live again.
            logger.warning("DEM cache write failed for %s/%s", cache_key, demtype, exc_info=True)

    def _ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)

    @staticmethod
    def _object_name(cache_key: str, demtype: str) -> str:
        return f"dem/{cache_key}/{demtype}.tif"


class DiskDemCache:
    """The same interface as DemCache, backed by local files. For hosts with
    no object store: each API instance keeps its own copy, which still
    spends OpenTopography's daily quota at most once per area per instance.
    Same contract as DemCache -- every failure is a miss, never an error."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def get(self, cache_key: str, demtype: str) -> bytes | None:
        try:
            return self._path(cache_key, demtype).read_bytes()
        except OSError:
            return None

    def put(self, cache_key: str, demtype: str, raw: bytes) -> None:
        path = self._path(cache_key, demtype)
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            # Write-then-rename, so a concurrent reader never sees half a file.
            partial = path.with_suffix(f".{os.getpid()}.part")
            partial.write_bytes(raw)
            partial.replace(path)
        except OSError:
            logger.warning("disk DEM cache write failed for %s/%s", cache_key, demtype, exc_info=True)

    def _path(self, cache_key: str, demtype: str) -> Path:
        # Hashed, so no key -- however it's spelled -- can name a path
        # outside the cache directory.
        digest = hashlib.sha256(f"{cache_key}/{demtype}".encode()).hexdigest()
        return self._directory / f"{digest}.tif"

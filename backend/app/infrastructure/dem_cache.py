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

import logging
from io import BytesIO

from minio import Minio

from app.core.config import Settings

logger = logging.getLogger(__name__)


class DemCache:
    def __init__(self, client: Minio, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    @classmethod
    def from_settings(cls, settings: Settings) -> "DemCache":
        client = Minio(
            settings.object_storage_endpoint,
            access_key=settings.object_storage_access_key,
            secret_key=settings.object_storage_secret_key,
            secure=settings.object_storage_secure,
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

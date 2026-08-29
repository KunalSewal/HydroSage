"""Redis-backed cache for a computed CatchmentResult, keyed by village id.

Exists so a village's D8 catchment delineation -- the CPU-heavy part of
analyze_catchment, not just its DEM input -- doesn't get recomputed from
scratch every time a different endpoint needs it for the same site. Both
GET /villages/{id}/elevation and POST /villages/{id}/recommend need it;
without this, "Analyze this site" then "Get pond recommendation" would
silently run the full fill_pits/fill_depressions/resolve_flats/flowdir/
accumulation/catchment-trace pipeline twice on identical data.

Short TTL: this is a within-a-browsing-session optimization, not a
durable store -- the DEM itself is what's durably cached (MinIO, see
dem_cache.py). Every failure mode (Redis down, a corrupted entry)
degrades to "cache miss, recompute" rather than raising, same as
dem_cache.py: caching here is an optimization, not a correctness
requirement.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import asdict

import redis

from app.core.config import Settings
from app.domain.catchment import CatchmentResult

logger = logging.getLogger(__name__)

TTL_SECONDS = 3600


class CatchmentCache:
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> "CatchmentCache":
        return cls(redis.Redis.from_url(settings.redis_url))

    def get(self, village_id: str) -> CatchmentResult | None:
        try:
            raw = self._client.get(self._key(village_id))
        except Exception:  # noqa: BLE001 -- a cache outage must fall back to a fresh computation
            logger.warning("catchment cache read failed, will recompute", exc_info=True)
            return None

        if raw is None:
            return None

        try:
            payload = raw.decode() if isinstance(raw, bytes) else raw
            return CatchmentResult(**json.loads(payload))
        except Exception:  # noqa: BLE001 -- a corrupted/stale entry must not break the request
            logger.warning("catchment cache entry unreadable, will recompute", exc_info=True)
            return None

    def put(self, village_id: str, result: CatchmentResult) -> None:
        try:
            self._client.set(self._key(village_id), json.dumps(asdict(result)), ex=TTL_SECONDS)
        except Exception:  # noqa: BLE001 -- a failed write must not fail the request that triggered it
            logger.warning("catchment cache write failed for %s", village_id, exc_info=True)

    def get_or_compute(self, village_id: str, compute: Callable[[], CatchmentResult]) -> CatchmentResult:
        """Cache-agnostic to what `compute` does -- callers pass
        `lambda: analyze_catchment(...)`, keeping this class unaware of
        the domain function it's caching, which is the only reason two
        different endpoints can share it without infrastructure/ needing
        to depend on domain/ at import time beyond the CatchmentResult
        shape itself."""
        cached = self.get(village_id)
        if cached is not None:
            return cached
        result = compute()
        self.put(village_id, result)
        return result

    @staticmethod
    def _key(village_id: str) -> str:
        return f"catchment:{village_id}"

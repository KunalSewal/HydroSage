"""Client for OpenTopography's Global DEM API (Copernicus GLO-30, ~30m).

Replaced OpenZenith after it proved unreliable mid-project — see
docs/DECISIONS.md D-005 for the live verification data behind this switch.
"""

from dataclasses import dataclass

import httpx
import numpy as np
from rasterio.io import MemoryFile

from app.core.config import get_settings
from app.infrastructure.dem_cache import DemCache


@dataclass(frozen=True)
class BoundingBox:
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float


class ElevationClient:
    def __init__(self, client: httpx.Client | None = None, cache: DemCache | None = None) -> None:
        settings = get_settings()
        self._api_key = settings.opentopography_api_key
        self._client = client or httpx.Client(
            base_url=settings.opentopography_base_url, timeout=30.0
        )
        self._cache = cache if cache is not None else DemCache.from_settings(settings)

    def get_dem_for_bbox(
        self, bbox: BoundingBox, demtype: str = "COP30", cache_key: str | None = None
    ) -> tuple[np.ndarray, BoundingBox]:
        """`cache_key` (typically a village id) lets repeat calls for the
        same site skip OpenTopography entirely -- its free tier is 50
        calls/day. Omit it to always fetch live, uncached."""
        raw = self._cache.get(cache_key, demtype) if cache_key is not None else None

        if raw is None:
            response = self._client.get(
                "/globaldem",
                params={
                    "demtype": demtype,
                    "south": bbox.min_lat,
                    "north": bbox.max_lat,
                    "west": bbox.min_lon,
                    "east": bbox.max_lon,
                    "outputFormat": "GTiff",
                    "API_Key": self._api_key,
                },
            )
            response.raise_for_status()
            raw = response.content
            if cache_key is not None:
                self._cache.put(cache_key, demtype, raw)

        with MemoryFile(raw) as memfile, memfile.open() as dataset:
            elevation = dataset.read(1).astype(np.float64)
            covered = BoundingBox(
                min_lon=dataset.bounds.left,
                min_lat=dataset.bounds.bottom,
                max_lon=dataset.bounds.right,
                max_lat=dataset.bounds.top,
            )

        return elevation, covered

    def close(self) -> None:
        self._client.close()

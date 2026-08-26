"""Client for OpenTopography's Global DEM API (Copernicus GLO-30, ~30m).

Replaced OpenZenith after it proved unreliable mid-project — see
docs/DECISIONS.md D-005 for the live verification data behind this switch.
"""

import io
from dataclasses import dataclass

import httpx
import numpy as np
import rasterio
from rasterio.io import MemoryFile

from app.core.config import get_settings


@dataclass(frozen=True)
class BoundingBox:
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float


class ElevationClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        settings = get_settings()
        self._api_key = settings.opentopography_api_key
        self._client = client or httpx.Client(
            base_url=settings.opentopography_base_url, timeout=30.0
        )

    def get_dem_for_bbox(
        self, bbox: BoundingBox, demtype: str = "COP30"
    ) -> tuple[np.ndarray, BoundingBox]:
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

        with MemoryFile(response.content) as memfile, memfile.open() as dataset:
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

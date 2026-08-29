"""Client for OpenStreetMap's Overpass API -- queries buildings, water
bodies, residential/industrial/commercial zones, and roads within a bbox,
used as an exclusion mask for available-land estimation
(domain/land_availability.py). No official government land-record API
exists for this (PROJECT_BRIEF.md open question #1); OSM coverage is the
documented proxy, per ARCHITECTURE.md.

Only `way` elements are queried/handled -- covers the large majority of
real-world tagged features; multipolygon `relation`s (e.g. a lake made of
multiple ways) are out of scope for this first version.
"""

from dataclasses import dataclass
from typing import Literal

import httpx

from app.core.config import get_settings
from app.infrastructure.elevation_client import BoundingBox

_QUERY_TEMPLATE = """
[out:json][timeout:25];
(
  way["building"]({south},{west},{north},{east});
  way["natural"="water"]({south},{west},{north},{east});
  way["landuse"="residential"]({south},{west},{north},{east});
  way["landuse"="industrial"]({south},{west},{north},{east});
  way["landuse"="commercial"]({south},{west},{north},{east});
  way["highway"]({south},{west},{north},{east});
);
out geom;
"""


@dataclass(frozen=True)
class ExcludedFeature:
    kind: Literal["area", "line"]
    coordinates: list[tuple[float, float]]  # [(lon, lat), ...]


class LandUseClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        settings = get_settings()
        # Some Overpass mirrors reject requests carrying a generic/bot-like
        # default User-Agent (httpx's default got a 403 from one) -- reuse
        # the same descriptive one Nominatim usage policy already requires.
        # A shorter timeout than the other clients: this lookup is a
        # best-effort, non-critical refinement (see _get_land_availability
        # in api/recommend.py), so a slow/unreachable Overpass instance
        # shouldn't make the whole recommendation wait 30s+ to degrade.
        self._client = client or httpx.Client(
            base_url=settings.overpass_base_url,
            timeout=10.0,
            headers={"User-Agent": settings.nominatim_user_agent},
        )

    def get_excluded_features(self, bbox: BoundingBox) -> list[ExcludedFeature]:
        query = _QUERY_TEMPLATE.format(
            south=bbox.min_lat, west=bbox.min_lon, north=bbox.max_lat, east=bbox.max_lon
        )
        response = self._client.post("/api/interpreter", content=query)
        response.raise_for_status()
        body = response.json()

        features = []
        for element in body.get("elements", []):
            geometry = element.get("geometry")
            if not geometry:
                continue
            coordinates = [(node["lon"], node["lat"]) for node in geometry]
            kind: Literal["area", "line"] = "line" if "highway" in element.get("tags", {}) else "area"
            features.append(ExcludedFeature(kind=kind, coordinates=coordinates))
        return features

    def close(self) -> None:
        self._client.close()

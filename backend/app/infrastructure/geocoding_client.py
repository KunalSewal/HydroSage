"""Client for Nominatim (OpenStreetMap) geocoding. See docs/DECISIONS.md D-005."""

import httpx

from app.core.config import get_settings


class GeocodingClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        settings = get_settings()
        self._client = client or httpx.Client(
            base_url=settings.nominatim_base_url,
            timeout=15.0,
            headers={"User-Agent": settings.nominatim_user_agent},
        )

    def search(self, query: str, limit: int = 5) -> list[dict]:
        response = self._client.get(
            "/search", params={"q": query, "format": "jsonv2", "limit": limit}
        )
        response.raise_for_status()
        return response.json()

    def reverse(self, lat: float, lon: float) -> dict | None:
        response = self._client.get(
            "/reverse", params={"lat": lat, "lon": lon, "format": "jsonv2"}
        )
        response.raise_for_status()
        data = response.json()
        return None if "error" in data else data

    def close(self) -> None:
        self._client.close()

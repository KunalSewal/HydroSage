"""Client for OpenZenith's elevation and DEM-tile endpoints.

Terrarium tile decoding: elevation = R*256 + G + B/256 - 32768.
https://github.com/tilezen/joerd/blob/master/docs/formats.md#terrarium
"""

import io
import math
from dataclasses import dataclass

import httpx
import numpy as np

from app.core.config import get_settings

_TERRARIUM_OFFSET = 32768


@dataclass(frozen=True)
class Tile:
    z: int
    x: int
    y: int


@dataclass(frozen=True)
class BoundingBox:
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float


def _lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def _tile_bounds(tile: Tile) -> BoundingBox:
    n = 2**tile.z

    def lat_at(y: int) -> float:
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))

    return BoundingBox(
        min_lon=tile.x / n * 360.0 - 180.0,
        max_lon=(tile.x + 1) / n * 360.0 - 180.0,
        min_lat=lat_at(tile.y + 1),
        max_lat=lat_at(tile.y),
    )


def tiles_covering_bbox(bbox: BoundingBox, z: int) -> list[Tile]:
    x_min, y_max = _lonlat_to_tile(bbox.min_lon, bbox.min_lat, z)
    x_max, y_min = _lonlat_to_tile(bbox.max_lon, bbox.max_lat, z)
    return [
        Tile(z=z, x=x, y=y)
        for y in range(y_min, y_max + 1)
        for x in range(x_min, x_max + 1)
    ]


def decode_terrarium_png(png_bytes: bytes) -> np.ndarray:
    from PIL import Image

    image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    arr = np.asarray(image).astype(np.int64)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    return (r * 256 + g + b / 256.0) - _TERRARIUM_OFFSET


class ElevationClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        settings = get_settings()
        self._base_url = settings.elevation_api_base_url.rsplit("/elevation", 1)[0]
        self._client = client or httpx.Client(base_url=self._base_url, timeout=15.0)

    def get_point_elevation(self, lat: float, lon: float) -> float:
        response = self._client.get("/elevation", params={"lat": lat, "lon": lon})
        response.raise_for_status()
        return response.json()["elevation"]

    def get_batch_elevation(self, points: list[tuple[float, float]]) -> list[float]:
        if len(points) > 2000:
            raise ValueError("OpenZenith batch elevation supports at most 2000 points per request")
        payload = {"points": [{"lat": lat, "lon": lon} for lat, lon in points]}
        response = self._client.post("/elevation/batch", json=payload)
        response.raise_for_status()
        return [r["elevation"] for r in response.json()["results"]]

    def get_dem_tile(self, tile: Tile) -> np.ndarray:
        response = self._client.get(f"/dem-tile/{tile.z}/{tile.x}/{tile.y}")
        response.raise_for_status()
        return decode_terrarium_png(response.content)

    def get_dem_for_bbox(self, bbox: BoundingBox, zoom: int) -> tuple[np.ndarray, BoundingBox]:
        """Fetch and mosaic DEM tiles covering bbox at the given zoom. Returns
        (elevation grid, bounding box actually covered by the mosaic — snapped
        to tile edges, so it's usually slightly larger than the input bbox)."""
        tiles = tiles_covering_bbox(bbox, zoom)
        xs = sorted({t.x for t in tiles})
        ys = sorted({t.y for t in tiles})
        tile_size = 256
        mosaic = np.empty((len(ys) * tile_size, len(xs) * tile_size), dtype=np.float64)

        for tile in tiles:
            row = ys.index(tile.y)
            col = xs.index(tile.x)
            grid = self.get_dem_tile(tile)
            mosaic[
                row * tile_size : (row + 1) * tile_size,
                col * tile_size : (col + 1) * tile_size,
            ] = grid

        top_left = _tile_bounds(Tile(zoom, xs[0], ys[0]))
        bottom_right = _tile_bounds(Tile(zoom, xs[-1], ys[-1]))
        covered = BoundingBox(
            min_lon=top_left.min_lon,
            max_lat=top_left.max_lat,
            max_lon=bottom_right.max_lon,
            min_lat=bottom_right.min_lat,
        )
        return mosaic, covered

    def close(self) -> None:
        self._client.close()

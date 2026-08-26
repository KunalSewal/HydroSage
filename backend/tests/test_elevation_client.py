import io
import os

import numpy as np
import pytest
from PIL import Image

from app.infrastructure.elevation_client import (
    BoundingBox,
    ElevationClient,
    Tile,
    decode_terrarium_png,
    tiles_covering_bbox,
)


def _encode_terrarium_png(elevation: float) -> bytes:
    value = int(elevation) + 32768
    r, rem = divmod(value, 256)
    g = rem
    b = 0
    arr = np.full((4, 4, 3), (r, g, b), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr, mode="RGB").save(buf, format="PNG")
    return buf.getvalue()


def test_decode_terrarium_png_round_trips_known_elevation():
    png_bytes = _encode_terrarium_png(855.0)
    grid = decode_terrarium_png(png_bytes)
    assert grid.shape == (4, 4)
    assert np.allclose(grid, 855.0)


def test_tiles_covering_bbox_is_at_least_one_tile():
    # Hiware Bazar, Maharashtra — see docs/DECISIONS.md D-004
    bbox = BoundingBox(min_lon=74.55, min_lat=19.02, max_lon=74.65, max_lat=19.12)
    tiles = tiles_covering_bbox(bbox, z=12)
    assert len(tiles) >= 1
    assert all(isinstance(t, Tile) and t.z == 12 for t in tiles)


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="hits the live OpenZenith API; set RUN_INTEGRATION_TESTS=1 to run",
)
def test_point_elevation_matches_dem_tile_for_hiware_bazar():
    client = ElevationClient()
    lat, lon = 19.0679874, 74.6012297

    point_elevation = client.get_point_elevation(lat, lon)

    bbox = BoundingBox(min_lon=lon - 0.01, min_lat=lat - 0.01, max_lon=lon + 0.01, max_lat=lat + 0.01)
    mosaic, _ = client.get_dem_for_bbox(bbox, zoom=12)

    assert 0 < point_elevation < 2000
    assert mosaic.min() <= point_elevation <= mosaic.max() + 50
    client.close()

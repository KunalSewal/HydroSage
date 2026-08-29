import numpy as np
import pytest

from app.domain.terrain import _nice_interval, _smooth, generate_contours
from app.infrastructure.elevation_client import BoundingBox


def test_generate_contours_on_a_cone():
    size = 50
    y, x = np.mgrid[0:size, 0:size]
    center = size / 2
    elevation = 100 - np.sqrt((x - center) ** 2 + (y - center) ** 2)

    bbox = BoundingBox(min_lon=74.0, min_lat=19.0, max_lon=74.1, max_lat=19.1)
    contours = generate_contours(elevation, bbox, interval=5)

    assert len(contours) > 0
    for contour in contours:
        for lon, lat in contour["coordinates"]:
            assert bbox.min_lon <= lon <= bbox.max_lon
            assert bbox.min_lat <= lat <= bbox.max_lat


def test_generate_contours_on_flat_surface_returns_nothing():
    elevation = np.full((10, 10), 42.0)
    bbox = BoundingBox(min_lon=0, min_lat=0, max_lon=1, max_lat=1)
    assert generate_contours(elevation, bbox) == []


def test_generate_contours_tags_each_line_with_its_level():
    size = 50
    y, x = np.mgrid[0:size, 0:size]
    center = size / 2
    elevation = 100 - np.sqrt((x - center) ** 2 + (y - center) ** 2)
    bbox = BoundingBox(min_lon=74.0, min_lat=19.0, max_lon=74.1, max_lat=19.1)

    contours = generate_contours(elevation, bbox, interval=10)

    levels = {c["elevation"] for c in contours}
    assert len(levels) > 1  # multiple distinct elevation bands, not one flat value


def test_generate_contours_auto_picks_an_interval_without_one_given():
    size = 50
    y, x = np.mgrid[0:size, 0:size]
    center = size / 2
    elevation = 100 - np.sqrt((x - center) ** 2 + (y - center) ** 2)
    bbox = BoundingBox(min_lon=74.0, min_lat=19.0, max_lon=74.1, max_lat=19.1)

    contours = generate_contours(elevation, bbox)

    levels = {c["elevation"] for c in contours}
    assert 3 <= len(levels) <= 15  # a readable number of bands, not 1 and not 100


def test_smooth_knocks_down_a_single_pixel_spike():
    flat = np.full((20, 20), 100.0)
    spiky = flat.copy()
    spiky[10, 10] = 200.0  # a single noisy DEM pixel, e.g. sensor/measurement noise

    smoothed = _smooth(spiky)

    assert smoothed.shape == spiky.shape
    assert smoothed[10, 10] < 150.0  # the spike is meaningfully knocked down
    assert smoothed[0, 0] == pytest.approx(100.0, abs=0.5)  # far from the spike, basically unchanged


def test_generate_contours_is_not_derailed_by_pixel_noise():
    size = 50
    y, x = np.mgrid[0:size, 0:size]
    center = size / 2
    cone = 100 - np.sqrt((x - center) ** 2 + (y - center) ** 2)
    rng = np.random.default_rng(seed=42)
    noisy = cone + rng.normal(scale=0.5, size=cone.shape)
    bbox = BoundingBox(min_lon=74.0, min_lat=19.0, max_lon=74.1, max_lat=19.1)

    contours = generate_contours(noisy, bbox, interval=10)

    assert len(contours) > 0
    for contour in contours:
        for lon, lat in contour["coordinates"]:
            assert bbox.min_lon <= lon <= bbox.max_lon
            assert bbox.min_lat <= lat <= bbox.max_lat


@pytest.mark.parametrize(
    "z_min,z_max,expected",
    [
        (0, 100, 20),  # span 100 over ~8 target levels -> round to 20
        (0, 10, 2),  # span 10 -> round to 2
        (267, 298, 5),  # real sample KML's elevation range -> round to 5
        (0, 1, 0.2),  # near-flat span -> still a sane sub-metre interval
    ],
)
def test_nice_interval_picks_round_numbers(z_min, z_max, expected):
    assert _nice_interval(z_min, z_max) == pytest.approx(expected)

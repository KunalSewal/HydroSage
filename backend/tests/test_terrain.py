import numpy as np

from app.domain.terrain import generate_contours
from app.infrastructure.elevation_client import BoundingBox


def test_generate_contours_on_a_cone():
    size = 50
    y, x = np.mgrid[0:size, 0:size]
    center = size / 2
    elevation = 100 - np.sqrt((x - center) ** 2 + (y - center) ** 2)

    bbox = BoundingBox(min_lon=74.0, min_lat=19.0, max_lon=74.1, max_lat=19.1)
    contours = generate_contours(elevation, bbox, num_levels=5)

    assert len(contours) > 0
    for contour in contours:
        for lon, lat in contour["coordinates"]:
            assert bbox.min_lon <= lon <= bbox.max_lon
            assert bbox.min_lat <= lat <= bbox.max_lat


def test_generate_contours_on_flat_surface_returns_nothing():
    elevation = np.full((10, 10), 42.0)
    bbox = BoundingBox(min_lon=0, min_lat=0, max_lon=1, max_lat=1)
    assert generate_contours(elevation, bbox) == []

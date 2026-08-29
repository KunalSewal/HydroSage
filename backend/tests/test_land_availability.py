import math

import pytest

from app.domain.land_availability import estimate_available_land
from app.infrastructure.elevation_client import BoundingBox
from app.infrastructure.land_use_client import ExcludedFeature

METERS_PER_DEGREE_LAT = 111_320.0
_TEST_LAT = 19.0


def _square_km_bbox() -> BoundingBox:
    # An actual ~1km x 1km square in *metres*, not degrees -- a degree of
    # longitude is shorter than a degree of latitude away from the
    # equator, so the two deltas need different sizes to square up.
    lat_deg = 1000 / METERS_PER_DEGREE_LAT
    lon_deg = 1000 / (METERS_PER_DEGREE_LAT * math.cos(math.radians(_TEST_LAT)))
    return BoundingBox(min_lon=74.0, min_lat=_TEST_LAT, max_lon=74.0 + lon_deg, max_lat=_TEST_LAT + lat_deg)


def test_estimate_available_land_with_no_excluded_features_is_the_whole_bbox():
    bbox = _square_km_bbox()
    result = estimate_available_land(bbox, excluded_features=[])
    assert result.available_area_m2 == pytest.approx(1_000_000, rel=0.02)  # ~1 sq km
    assert result.excluded_feature_count == 0


def test_estimate_available_land_subtracts_a_building_footprint():
    bbox = _square_km_bbox()
    # A building covering the western half of the bbox, roughly.
    half_lon = (bbox.min_lon + bbox.max_lon) / 2
    building = ExcludedFeature(
        kind="area",
        coordinates=[
            (bbox.min_lon, bbox.min_lat),
            (half_lon, bbox.min_lat),
            (half_lon, bbox.max_lat),
            (bbox.min_lon, bbox.max_lat),
            (bbox.min_lon, bbox.min_lat),
        ],
    )

    result = estimate_available_land(bbox, excluded_features=[building])

    assert result.available_area_m2 == pytest.approx(500_000, rel=0.05)
    assert result.excluded_feature_count == 1


def test_estimate_available_land_buffers_a_road_line_into_an_excludable_area():
    bbox = _square_km_bbox()
    mid_lat = (bbox.min_lat + bbox.max_lat) / 2
    road = ExcludedFeature(kind="line", coordinates=[(bbox.min_lon, mid_lat), (bbox.max_lon, mid_lat)])

    result = estimate_available_land(bbox, excluded_features=[road])

    # A line has zero area on its own -- some meaningful area must have
    # been excluded (the buffered road strip), but nowhere near the whole
    # bbox, since it's just a thin strip across the middle.
    assert 0 < result.available_area_m2 < 1_000_000


def test_estimate_available_land_never_goes_negative_even_if_excluded_area_overlaps_and_exceeds_bbox():
    bbox = _square_km_bbox()
    # A "building" deliberately larger than the bbox itself.
    oversized = ExcludedFeature(
        kind="area",
        coordinates=[
            (bbox.min_lon - 0.01, bbox.min_lat - 0.01),
            (bbox.max_lon + 0.01, bbox.min_lat - 0.01),
            (bbox.max_lon + 0.01, bbox.max_lat + 0.01),
            (bbox.min_lon - 0.01, bbox.max_lat + 0.01),
            (bbox.min_lon - 0.01, bbox.min_lat - 0.01),
        ],
    )

    result = estimate_available_land(bbox, excluded_features=[oversized])

    assert result.available_area_m2 == pytest.approx(0, abs=1.0)


def test_estimate_available_land_ignores_a_degenerate_feature_with_too_few_points():
    bbox = _square_km_bbox()
    degenerate = ExcludedFeature(kind="area", coordinates=[(bbox.min_lon, bbox.min_lat)])

    result = estimate_available_land(bbox, excluded_features=[degenerate])

    assert result.available_area_m2 == pytest.approx(1_000_000, rel=0.02)

import numpy as np
import pytest

from app.domain.area import (
    MAX_SPAN_DEG,
    MIN_AREA_M2,
    analysis_bbox_for,
    polygon_area_m2,
    rasterize_polygon,
    validate_area,
)
from app.infrastructure.elevation_client import BoundingBox

# ~1.1 km x ~1.1 km square near Bhilai, as [lon, lat] -- GeoJSON order.
SQUARE = [[81.30, 21.20], [81.31, 21.20], [81.31, 21.21], [81.30, 21.21]]


def test_polygon_area_of_a_small_square_matches_its_ground_size():
    # 0.01 deg of latitude is ~1113 m; 0.01 deg of longitude at 21.2N is ~1038 m.
    area = polygon_area_m2(SQUARE)
    assert area == pytest.approx(1113.2 * 1037.9, rel=0.01)


def test_polygon_area_ignores_winding_and_an_explicit_closing_point():
    clockwise_closed = list(reversed(SQUARE)) + [SQUARE[-1]]
    assert polygon_area_m2(clockwise_closed) == pytest.approx(polygon_area_m2(SQUARE))


def test_validate_area_accepts_a_reasonable_polygon():
    validate_area(SQUARE)  # does not raise


def test_validate_area_rejects_fewer_than_three_points():
    with pytest.raises(ValueError, match="at least 3"):
        validate_area(SQUARE[:2])


def test_validate_area_rejects_an_area_too_small_to_hold_a_catchment():
    side = 0.0005  # ~50 m square, ~0.25 ha
    tiny = [[81.3, 21.2], [81.3 + side, 21.2], [81.3 + side, 21.2 + side], [81.3, 21.2 + side]]
    assert polygon_area_m2(tiny) < MIN_AREA_M2
    with pytest.raises(ValueError, match="too small"):
        validate_area(tiny)


def test_validate_area_rejects_a_span_too_large_for_the_memory_budget():
    wide = [[81.0, 21.2], [81.0 + MAX_SPAN_DEG * 1.5, 21.2], [81.0 + MAX_SPAN_DEG * 1.5, 21.21], [81.0, 21.21]]
    with pytest.raises(ValueError, match="too large"):
        validate_area(wide)


def test_validate_area_rejects_out_of_range_coordinates():
    with pytest.raises(ValueError, match="coordinates"):
        validate_area([[200.0, 21.2], [81.31, 21.2], [81.31, 21.21]])


def test_analysis_bbox_pads_beyond_the_polygon_on_every_side():
    bbox = analysis_bbox_for(SQUARE)
    assert bbox.min_lon < 81.30 and bbox.max_lon > 81.31
    assert bbox.min_lat < 21.20 and bbox.max_lat > 21.21


def test_rasterize_polygon_marks_only_cells_inside():
    bbox = BoundingBox(min_lon=0.0, min_lat=0.0, max_lon=10.0, max_lat=10.0)
    # Left half of the raster.
    ring = [[0.0, 0.0], [5.0, 0.0], [5.0, 10.0], [0.0, 10.0]]

    mask = rasterize_polygon(ring, bbox, shape=(10, 10))

    assert mask.dtype == bool
    assert mask[:, :5].all()
    assert not mask[:, 5:].any()


def test_rasterize_polygon_puts_north_in_row_zero():
    bbox = BoundingBox(min_lon=0.0, min_lat=0.0, max_lon=10.0, max_lat=10.0)
    top_half = [[0.0, 5.0], [10.0, 5.0], [10.0, 10.0], [0.0, 10.0]]

    mask = rasterize_polygon(top_half, bbox, shape=(10, 10))

    assert mask[:5, :].all()
    assert not mask[5:, :].any()
    assert np.count_nonzero(mask) == 50


def test_validate_area_accepts_a_span_of_exactly_the_limit():
    # 81.26 - 81.20 is 0.0600000000000023 in floating point; drawing right
    # up to the limit must not be rejected over that rounding.
    lo, la = 81.20, 21.10
    edge = [[lo, la], [lo + MAX_SPAN_DEG, la], [lo + MAX_SPAN_DEG, la + MAX_SPAN_DEG], [lo, la + MAX_SPAN_DEG]]
    validate_area(edge)  # does not raise

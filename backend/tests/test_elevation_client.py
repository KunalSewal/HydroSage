import os

import numpy as np
import pytest

from app.infrastructure.elevation_client import BoundingBox, ElevationClient


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="hits the live OpenTopography API; set RUN_INTEGRATION_TESTS=1 to run",
)
def test_get_dem_for_bbox_returns_plausible_elevation_for_hiware_bazar():
    client = ElevationClient()
    # Hiware Bazar, Maharashtra — see docs/DECISIONS.md D-004. Known range
    # from a prior verified call: 662.8-959.2m for this exact bbox.
    bbox = BoundingBox(min_lon=74.53125, min_lat=19.020577, max_lon=74.663086, max_lat=19.103648)

    elevation, covered = client.get_dem_for_bbox(bbox)

    assert isinstance(elevation, np.ndarray)
    assert elevation.ndim == 2
    assert 600 < elevation.min() < 700
    assert 900 < elevation.max() < 1000
    assert covered.min_lon == pytest.approx(bbox.min_lon, abs=0.01)
    assert covered.max_lat == pytest.approx(bbox.max_lat, abs=0.01)
    client.close()

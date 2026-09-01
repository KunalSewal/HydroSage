"""Orchestrates rainfall -> runoff -> pond sizing -> land-availability into
one result, given a location and a catchment area already computed
upstream. Shared by both endpoints that need it: the click-map
POST /villages/{id}/recommend (a village's stored location) and the
KML-upload POST /analyzeContour (the uploaded survey's own bbox centroid
-- there's no "village" for an uploaded file to hang the lookup off).

Deliberately its own layer, distinct from app/domain/ (pure calculation,
no I/O -- see docs/ARCHITECTURE.md) and app/api/ (HTTP concerns only, no
business logic). This function does real I/O (RainfallClient,
LandUseClient) orchestrating multiple domain functions, which is neither
-- a thin "use case" layer. Each piece it calls is independently
unit-tested (domain/rainfall.py, domain/runoff.py, domain/pond.py,
domain/land_availability.py); this function itself is exercised via the
two endpoints' live verification rather than mocked unit tests, same as
this codebase's existing endpoint-level orchestration (e.g. the elevation
endpoint's own inline client-then-domain-function calls).
"""

import logging
from datetime import date

from app.domain.land_availability import estimate_available_land
from app.domain.pond import size_pond_from_terrain_capacity
from app.domain.rainfall import summarize_rainfall
from app.domain.runoff import estimate_annual_runoff_volume
from app.infrastructure.elevation_client import BoundingBox
from app.infrastructure.land_use_client import LandUseClient
from app.infrastructure.rainfall_client import RainfallClient
from app.schemas.recommend import PondOptionOut, RecommendationFieldsOut

logger = logging.getLogger(__name__)

RAINFALL_HISTORY_YEARS = 10


def _get_available_land_hectares(bbox: BoundingBox) -> float | None:
    """Land availability comes from a public, best-effort community API
    (Overpass) that isn't always reliable -- it shouldn't be able to fail
    the whole recommendation over an availability check the brief itself
    treats as a "checked against" refinement, not the core deliverable."""
    land_use_client = LandUseClient()
    try:
        excluded = land_use_client.get_excluded_features(bbox)
    except Exception:  # noqa: BLE001 -- see docstring
        logger.warning("land-availability lookup failed; recommending without a land check", exc_info=True)
        return None
    finally:
        land_use_client.close()
    return estimate_available_land(bbox, excluded).available_area_m2


def compute_recommendation_fields(
    lat: float,
    lon: float,
    bbox: BoundingBox,
    catchment_area_m2: float,
    achievable_volume_m3_by_depth: dict[float, float],
) -> RecommendationFieldsOut:
    end_year = date.today().year - 1
    start = date(end_year - RAINFALL_HISTORY_YEARS + 1, 1, 1)
    end = date(end_year, 12, 31)

    rainfall_client = RainfallClient()
    try:
        daily = rainfall_client.get_daily_rainfall(lat, lon, start, end)
    finally:
        rainfall_client.close()
    rainfall = summarize_rainfall(daily)

    runoff = estimate_annual_runoff_volume(
        average_annual_rainfall_mm=rainfall.average_annual_mm,
        catchment_area_m2=catchment_area_m2,
    )
    pond_options = size_pond_from_terrain_capacity(achievable_volume_m3_by_depth)
    available_land_m2 = _get_available_land_hectares(bbox)

    return RecommendationFieldsOut(
        average_annual_rainfall_mm=rainfall.average_annual_mm,
        runoff_volume_m3=runoff.runoff_volume_m3,
        runoff_coefficient=runoff.runoff_coefficient,
        pond_options=[
            PondOptionOut(
                depth_m=o.depth_m,
                surface_area_m2=o.surface_area_m2,
                side_length_m=o.side_length_m,
                fits_available_land=(o.surface_area_m2 <= available_land_m2) if available_land_m2 is not None else None,
                annual_runoff_capture_fraction=(
                    achievable_volume_m3_by_depth[o.depth_m] / runoff.runoff_volume_m3
                    if runoff.runoff_volume_m3 > 0
                    else None
                ),
            )
            for o in pond_options
        ],
        available_land_hectares=(available_land_m2 / 10_000) if available_land_m2 is not None else None,
    )

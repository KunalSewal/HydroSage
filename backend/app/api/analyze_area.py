import hashlib
import json
import logging

import httpx
from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.domain.area import analysis_bbox_for, polygon_area_m2, rasterize_polygon, validate_area
from app.domain.catchment import analyze_catchment
from app.domain.terrain import generate_contours
from app.infrastructure.catchment_cache import CatchmentCache
from app.infrastructure.elevation_client import BoundingBox, ElevationClient
from app.schemas.area import AreaAnalysisIn, AreaAnalysisOut
from app.schemas.catchment import BoundingBoxOut, catchment_fields
from app.services.recommendation import compute_recommendation_fields

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analyze-area"])


def _polygon_key(polygon: list[list[float]]) -> str:
    """A stable cache key for a drawn area. Rounded to 6 dp (~0.1 m) so the
    same shape re-sent from the frontend hits the same entry."""
    rounded = [[round(lon, 6), round(lat, 6)] for lon, lat, *_ in polygon]
    return "area-" + hashlib.sha1(json.dumps(rounded).encode()).hexdigest()[:16]


@router.post("/analyzeArea", response_model=AreaAnalysisOut)
def analyze_area(payload: AreaAnalysisIn):
    """Pond site, catchment, and expected water volume for a land area
    drawn on the map. The pond is sited inside the drawn polygon; its
    catchment may extend uphill beyond it (see domain/area.py)."""
    polygon = payload.polygon
    try:
        validate_area(polygon)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))

    key = _polygon_key(polygon)
    requested_bbox = analysis_bbox_for(polygon)

    elevation_client = ElevationClient()
    try:
        # Keyed by the drawn shape, so re-analyzing the same area never
        # spends another call from OpenTopography's 50-per-day quota.
        mosaic, covered = elevation_client.get_dem_for_bbox(requested_bbox, cache_key=key)
    except httpx.HTTPError as error:
        logger.warning("elevation fetch failed for drawn area", exc_info=True)
        raise HTTPException(status_code=502, detail=f"elevation service unavailable: {error}")
    finally:
        elevation_client.close()

    site_mask = rasterize_polygon(polygon, covered, mosaic.shape)

    catchment_cache = CatchmentCache.from_settings(get_settings())
    try:
        catchment = catchment_cache.get_or_compute(
            key, lambda: analyze_catchment(mosaic, covered, site_mask=site_mask)
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))

    contours = generate_contours(mosaic, covered)

    # Rainfall and land use are looked up for the drawn area itself, not
    # the padded analysis extent around it.
    lons = [p[0] for p in polygon]
    lats = [p[1] for p in polygon]
    polygon_bbox = BoundingBox(min_lon=min(lons), min_lat=min(lats), max_lon=max(lons), max_lat=max(lats))
    recommendation_fields = compute_recommendation_fields(
        (polygon_bbox.min_lat + polygon_bbox.max_lat) / 2,
        (polygon_bbox.min_lon + polygon_bbox.max_lon) / 2,
        polygon_bbox,
        catchment.catchment_area_m2,
        catchment.achievable_volume_m3_by_depth,
    )

    return AreaAnalysisOut(
        **catchment_fields(catchment).model_dump(),
        **recommendation_fields.model_dump(),
        source_bbox=BoundingBoxOut(
            min_lon=covered.min_lon, min_lat=covered.min_lat, max_lon=covered.max_lon, max_lat=covered.max_lat
        ),
        grid_resolution=max(mosaic.shape),
        min_elevation=float(mosaic.min()),
        max_elevation=float(mosaic.max()),
        contours=[{"elevation": c["elevation"], "coordinates": c["coordinates"]} for c in contours],
        selected_area=[[p[0], p[1]] for p in polygon],
        selected_area_hectares=polygon_area_m2(polygon) / 10_000,
    )

import uuid

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.catchment import analyze_catchment
from app.infrastructure.catchment_cache import CatchmentCache
from app.infrastructure.db import get_db
from app.infrastructure.elevation_client import BoundingBox, ElevationClient
from app.infrastructure.models import Village
from app.schemas.recommend import RecommendationOut
from app.services.recommendation import compute_recommendation_fields

router = APIRouter(prefix="/villages", tags=["recommend"])


@router.post("/{village_id}/recommend", response_model=RecommendationOut)
def get_recommendation(village_id: str, db: Session = Depends(get_db)):
    """Combines terrain/catchment, rainfall, runoff, and pond sizing into
    one result -- PROJECT_BRIEF.md core use case #8, overlaying everything
    for a single village."""
    try:
        village_uuid = uuid.UUID(village_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="village_id must be a UUID")

    village = db.get(Village, village_uuid)
    if village is None:
        raise HTTPException(status_code=404, detail="village not found")

    bounds = to_shape(village.bounds)
    min_lon, min_lat, max_lon, max_lat = bounds.bounds
    bbox = BoundingBox(min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat)

    elevation_client = ElevationClient()
    try:
        mosaic, covered = elevation_client.get_dem_for_bbox(bbox, cache_key=str(village.id))
    finally:
        elevation_client.close()
    catchment_cache = CatchmentCache.from_settings(get_settings())
    catchment = catchment_cache.get_or_compute(str(village.id), lambda: analyze_catchment(mosaic, covered))

    centroid = to_shape(village.centroid)
    fields = compute_recommendation_fields(centroid.y, centroid.x, bbox, catchment.catchment_area_m2)

    return RecommendationOut(
        village_id=village.id,
        catchment_area_hectares=catchment.catchment_area_m2 / 10_000,
        **fields.model_dump(),
    )

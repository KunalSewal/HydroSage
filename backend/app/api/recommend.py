import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from app.domain.catchment import analyze_catchment
from app.domain.pond import recommend_pond_dimensions
from app.domain.rainfall import summarize_rainfall
from app.domain.runoff import estimate_annual_runoff_volume
from app.infrastructure.db import get_db
from app.infrastructure.elevation_client import BoundingBox, ElevationClient
from app.infrastructure.models import Village
from app.infrastructure.rainfall_client import RainfallClient
from app.schemas.recommend import PondOptionOut, RecommendationOut

router = APIRouter(prefix="/villages", tags=["recommend"])

RAINFALL_HISTORY_YEARS = 10


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
    catchment = analyze_catchment(mosaic, covered)

    centroid = to_shape(village.centroid)
    end_year = date.today().year - 1
    start = date(end_year - RAINFALL_HISTORY_YEARS + 1, 1, 1)
    end = date(end_year, 12, 31)

    rainfall_client = RainfallClient()
    try:
        daily = rainfall_client.get_daily_rainfall(centroid.y, centroid.x, start, end)
    finally:
        rainfall_client.close()
    rainfall = summarize_rainfall(daily)

    runoff = estimate_annual_runoff_volume(
        average_annual_rainfall_mm=rainfall.average_annual_mm,
        catchment_area_m2=catchment.catchment_area_m2,
    )
    pond = recommend_pond_dimensions(target_storage_m3=runoff.runoff_volume_m3)

    return RecommendationOut(
        village_id=village.id,
        catchment_area_hectares=catchment.catchment_area_m2 / 10_000,
        average_annual_rainfall_mm=rainfall.average_annual_mm,
        runoff_volume_m3=runoff.runoff_volume_m3,
        runoff_coefficient=runoff.runoff_coefficient,
        pond_options=[
            PondOptionOut(depth_m=o.depth_m, surface_area_m2=o.surface_area_m2, side_length_m=o.side_length_m)
            for o in pond.options
        ],
    )

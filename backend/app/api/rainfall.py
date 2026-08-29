import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from app.domain.rainfall import summarize_rainfall
from app.infrastructure.db import get_db
from app.infrastructure.models import Village
from app.infrastructure.rainfall_client import RainfallClient
from app.schemas.rainfall import RainfallOut

router = APIRouter(prefix="/villages", tags=["rainfall"])

HISTORY_YEARS = 10


@router.get("/{village_id}/rainfall", response_model=RainfallOut)
def get_rainfall(village_id: str, db: Session = Depends(get_db)):
    try:
        village_uuid = uuid.UUID(village_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="village_id must be a UUID")

    village = db.get(Village, village_uuid)
    if village is None:
        raise HTTPException(status_code=404, detail="village not found")

    centroid = to_shape(village.centroid)
    end_year = date.today().year - 1  # the last *full* calendar year available
    start = date(end_year - HISTORY_YEARS + 1, 1, 1)
    end = date(end_year, 12, 31)

    client = RainfallClient()
    try:
        daily = client.get_daily_rainfall(centroid.y, centroid.x, start, end)
    finally:
        client.close()

    summary = summarize_rainfall(daily)

    return RainfallOut(
        village_id=village.id,
        period_start=summary.period_start,
        period_end=summary.period_end,
        average_annual_mm=summary.average_annual_mm,
        monthly_average_mm=summary.monthly_average_mm,
    )

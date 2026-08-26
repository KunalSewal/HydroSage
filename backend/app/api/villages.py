import uuid

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from app.domain.terrain import generate_contours
from app.infrastructure.db import get_db
from app.infrastructure.elevation_client import BoundingBox, ElevationClient
from app.infrastructure.models import Village
from app.schemas.village import BoundingBoxOut, ElevationOut, VillageOut

router = APIRouter(prefix="/villages", tags=["villages"])


@router.get("", response_model=list[VillageOut])
def list_villages(db: Session = Depends(get_db)):
    villages = db.query(Village).all()
    return [
        VillageOut(
            id=v.id,
            name=v.name,
            state=v.state,
            district=v.district,
            lon=to_shape(v.centroid).x,
            lat=to_shape(v.centroid).y,
        )
        for v in villages
    ]


@router.get("/{village_id}/elevation", response_model=ElevationOut)
def get_elevation(village_id: str, db: Session = Depends(get_db)):
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

    client = ElevationClient()
    try:
        mosaic, covered = client.get_dem_for_bbox(bbox)
    finally:
        client.close()

    contours = generate_contours(mosaic, covered)

    return ElevationOut(
        village_id=village.id,
        bbox=BoundingBoxOut(
            min_lon=covered.min_lon,
            min_lat=covered.min_lat,
            max_lon=covered.max_lon,
            max_lat=covered.max_lat,
        ),
        min_elevation=float(mosaic.min()),
        max_elevation=float(mosaic.max()),
        contours=[{"elevation": c["elevation"], "coordinates": c["coordinates"]} for c in contours],
    )

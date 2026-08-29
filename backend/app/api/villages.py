import uuid

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.catchment import analyze_catchment
from app.domain.terrain import generate_contours
from app.infrastructure.catchment_cache import CatchmentCache
from app.infrastructure.db import get_db
from app.infrastructure.elevation_client import BoundingBox, ElevationClient
from app.infrastructure.geocoding_client import GeocodingClient
from app.infrastructure.models import Village
from app.infrastructure.village_repository import create_village, find_nearby
from app.schemas.catchment import catchment_fields
from app.schemas.village import BoundingBoxOut, ElevationOut, VillageCreate, VillageOut

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


@router.post("", response_model=VillageOut)
def create_village_from_point(payload: VillageCreate, db: Session = Depends(get_db)):
    existing = find_nearby(db, lat=payload.lat, lon=payload.lon)
    if existing is not None:
        return VillageOut(
            id=existing.id,
            name=existing.name,
            state=existing.state,
            district=existing.district,
            lat=payload.lat,
            lon=payload.lon,
        )

    geocoder = GeocodingClient()
    try:
        place = geocoder.reverse(payload.lat, payload.lon)
    finally:
        geocoder.close()

    if place is None:
        raise HTTPException(status_code=422, detail="couldn't identify a site at this location")

    address = place.get("address", {})
    name = place.get("name") or address.get("city") or address.get("town") or address.get("village") or place["display_name"].split(",")[0]
    state = address.get("state", "")
    district = address.get("state_district") or address.get("county") or ""

    village = create_village(db, lat=payload.lat, lon=payload.lon, name=name, state=state, district=district)
    db.commit()

    return VillageOut(id=village.id, name=name, state=state, district=district, lat=payload.lat, lon=payload.lon)


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
        mosaic, covered = client.get_dem_for_bbox(bbox, cache_key=str(village.id))
    finally:
        client.close()

    contours = generate_contours(mosaic, covered)
    catchment_cache = CatchmentCache.from_settings(get_settings())
    catchment = catchment_cache.get_or_compute(str(village.id), lambda: analyze_catchment(mosaic, covered))

    return ElevationOut(
        **catchment_fields(catchment).model_dump(),
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

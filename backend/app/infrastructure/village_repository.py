import uuid

from geoalchemy2 import Geography
from geoalchemy2.elements import WKTElement
from geoalchemy2.functions import ST_DWithin
from geoalchemy2.shape import from_shape
from shapely.geometry import Point, box
from sqlalchemy import cast
from sqlalchemy.orm import Session

from app.infrastructure.models import Village

DEFAULT_HALF_EXTENT_DEG = 0.03  # ~3km — village + surrounding catchment, see D-004
FIND_NEARBY_RADIUS_M = 500.0


def find_nearby(db: Session, lat: float, lon: float, radius_m: float = FIND_NEARBY_RADIUS_M) -> Village | None:
    point = WKTElement(f"POINT({lon} {lat})", srid=4326)
    return (
        db.query(Village)
        .filter(ST_DWithin(cast(Village.centroid, Geography), cast(point, Geography), radius_m))
        .first()
    )


def create_village(
    db: Session, lat: float, lon: float, name: str, state: str, district: str
) -> Village:
    centroid = Point(lon, lat)
    e = DEFAULT_HALF_EXTENT_DEG
    bounds = box(lon - e, lat - e, lon + e, lat + e)

    village = Village(
        id=uuid.uuid4(),
        name=name,
        state=state,
        district=district,
        centroid=from_shape(centroid, srid=4326),
        bounds=from_shape(bounds, srid=4326),
    )
    db.add(village)
    return village

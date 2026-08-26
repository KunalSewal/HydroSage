import uuid

from pydantic import BaseModel


class VillageOut(BaseModel):
    id: uuid.UUID
    name: str
    state: str
    district: str
    lat: float
    lon: float


class Contour(BaseModel):
    elevation: float
    coordinates: list[list[float]]  # [[lon, lat], ...]


class BoundingBoxOut(BaseModel):
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float


class ElevationOut(BaseModel):
    village_id: uuid.UUID
    bbox: BoundingBoxOut
    min_elevation: float
    max_elevation: float
    contours: list[Contour]

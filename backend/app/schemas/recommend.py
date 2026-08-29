import uuid

from pydantic import BaseModel


class PondOptionOut(BaseModel):
    depth_m: float
    surface_area_m2: float
    side_length_m: float


class RecommendationOut(BaseModel):
    village_id: uuid.UUID
    catchment_area_hectares: float
    average_annual_rainfall_mm: float
    runoff_volume_m3: float
    runoff_coefficient: float
    pond_options: list[PondOptionOut]

import uuid

from pydantic import BaseModel


class PondOptionOut(BaseModel):
    depth_m: float
    surface_area_m2: float
    side_length_m: float
    # None when available-land data couldn't be determined (e.g. the
    # Overpass API was unreachable) -- absence of an answer, not "false".
    fits_available_land: bool | None


class RecommendationOut(BaseModel):
    village_id: uuid.UUID
    catchment_area_hectares: float
    average_annual_rainfall_mm: float
    runoff_volume_m3: float
    runoff_coefficient: float
    pond_options: list[PondOptionOut]
    available_land_hectares: float | None

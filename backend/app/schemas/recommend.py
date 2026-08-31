import uuid

from pydantic import BaseModel


class PondOptionOut(BaseModel):
    depth_m: float
    surface_area_m2: float
    side_length_m: float
    # None when available-land data couldn't be determined (e.g. the
    # Overpass API was unreachable) -- absence of an answer, not "false".
    fits_available_land: bool | None
    # None when the terrain's achievable volume at this depth couldn't be
    # determined -- same convention as fits_available_land.
    fits_terrain_capacity: bool | None


class RecommendationFieldsOut(BaseModel):
    """Rainfall -> runoff -> pond sizing -> land-availability check, shared
    by every endpoint that computes it (the click-map /recommend endpoint
    and the KML-upload /analyzeContour endpoint) so they return the same
    shape instead of two near-identical schemas."""

    average_annual_rainfall_mm: float
    runoff_volume_m3: float
    runoff_coefficient: float
    pond_options: list[PondOptionOut]
    available_land_hectares: float | None


class RecommendationOut(RecommendationFieldsOut):
    village_id: uuid.UUID
    catchment_area_hectares: float

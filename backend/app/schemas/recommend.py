import uuid

from pydantic import BaseModel


class PondOptionOut(BaseModel):
    depth_m: float
    surface_area_m2: float
    side_length_m: float
    # None when available-land data couldn't be determined (e.g. the
    # Overpass API was unreachable) -- absence of an answer, not "false".
    fits_available_land: bool | None
    # What share of a typical year's catchment runoff this depth's pond
    # holds. Bounded to at most 1.0, since the pond is never sized beyond
    # the runoff available to fill it. Exactly 1.0 means runoff-limited
    # (the terrain could hold more, but the catchment doesn't deliver
    # more); below 1.0 means terrain-limited. None only when
    # runoff_volume_m3 is exactly 0, to avoid dividing by zero.
    runoff_capture_ratio: float | None


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

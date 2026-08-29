from pydantic import BaseModel

from app.domain.catchment import CatchmentResult
from app.schemas.recommend import RecommendationFieldsOut


class BoundingBoxOut(BaseModel):
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float


class ContourOut(BaseModel):
    elevation: float
    coordinates: list[list[float]]  # [[lon, lat], ...]


class CatchmentFieldsOut(BaseModel):
    """The result of domain.catchment.analyze_catchment, shared by every
    endpoint that runs it (the KML-upload path and the click-map path) so
    they return the same shape instead of two near-identical schemas."""

    pond_location: dict[str, float]  # {"lat": ..., "lon": ...}
    catchment_area_m2: float
    catchment_area_hectares: float
    catchment_cell_count: int
    flow_accumulation_at_pond: float
    catchment_boundary: list[list[float]]  # [[lon, lat], ...], closed ring


class CatchmentAnalysisOut(CatchmentFieldsOut, RecommendationFieldsOut):
    source_bbox: BoundingBoxOut
    grid_resolution: int
    min_elevation: float
    max_elevation: float
    contours: list[ContourOut]


def catchment_fields(result: CatchmentResult) -> CatchmentFieldsOut:
    return CatchmentFieldsOut(
        pond_location={"lat": result.pond_lat, "lon": result.pond_lon},
        catchment_area_m2=result.catchment_area_m2,
        catchment_area_hectares=result.catchment_area_m2 / 10_000,
        catchment_cell_count=result.catchment_cell_count,
        flow_accumulation_at_pond=result.flow_accumulation_at_pond,
        catchment_boundary=result.catchment_boundary,
    )

from pydantic import BaseModel


class BoundingBoxOut(BaseModel):
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float


class ContourOut(BaseModel):
    elevation: float
    coordinates: list[list[float]]  # [[lon, lat], ...]


class CatchmentAnalysisOut(BaseModel):
    pond_location: dict[str, float]  # {"lat": ..., "lon": ...}
    catchment_area_m2: float
    catchment_area_hectares: float
    catchment_cell_count: int
    flow_accumulation_at_pond: float
    catchment_boundary: list[list[float]]  # [[lon, lat], ...], closed ring
    source_bbox: BoundingBoxOut
    grid_resolution: int
    min_elevation: float
    max_elevation: float
    contours: list[ContourOut]

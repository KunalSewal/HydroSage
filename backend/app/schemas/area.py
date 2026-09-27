from pydantic import BaseModel, Field

from app.schemas.catchment import CatchmentAnalysisOut


class AreaAnalysisIn(BaseModel):
    # [[lon, lat], ...] -- GeoJSON order, same as every coordinate this API
    # returns. A rectangle is sent as its four corners; the ring may be
    # closed (first == last) or open.
    polygon: list[list[float]] = Field(min_length=3)


class AreaAnalysisOut(CatchmentAnalysisOut):
    selected_area: list[list[float]]  # the polygon as received, [[lon, lat], ...]
    selected_area_hectares: float

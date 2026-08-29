import uuid

from pydantic import BaseModel


class RainfallOut(BaseModel):
    village_id: uuid.UUID
    period_start: str
    period_end: str
    average_annual_mm: float
    monthly_average_mm: list[float]  # 12 values, Jan..Dec

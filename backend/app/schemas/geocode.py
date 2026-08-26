from pydantic import BaseModel


class GeocodeResultOut(BaseModel):
    display_name: str
    lat: float
    lon: float

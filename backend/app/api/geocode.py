from fastapi import APIRouter, Query

from app.infrastructure.geocoding_client import GeocodingClient
from app.schemas.geocode import GeocodeResultOut

router = APIRouter(tags=["geocode"])


@router.get("/geocode", response_model=list[GeocodeResultOut])
def search_places(query: str = Query(..., min_length=1)):
    client = GeocodingClient()
    try:
        results = client.search(query)
    finally:
        client.close()
    return [
        GeocodeResultOut(display_name=r["display_name"], lat=float(r["lat"]), lon=float(r["lon"]))
        for r in results
    ]

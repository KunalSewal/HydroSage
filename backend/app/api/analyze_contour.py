from fastapi import APIRouter, HTTPException, UploadFile

from app.domain.catchment import analyze_catchment
from app.infrastructure.kml_parser import DEFAULT_GRID_SIZE, parse_contour_kml
from app.schemas.catchment import BoundingBoxOut, CatchmentAnalysisOut

router = APIRouter(tags=["analyze-contour"])


@router.post("/analyzeContour", response_model=CatchmentAnalysisOut)
async def analyze_contour(file: UploadFile):
    if not file.filename or not file.filename.lower().endswith(".kml"):
        raise HTTPException(status_code=422, detail="expected a .kml file")

    kml_bytes = await file.read()

    try:
        elevation, bbox = parse_contour_kml(kml_bytes)
    except Exception as error:  # noqa: BLE001 -- translating any malformed-upload
        # failure (XML parse errors, bad coordinate values, etc.) into a
        # clean 422 rather than a 500, since this is a user-uploaded file
        # whose failure modes we don't fully control.
        raise HTTPException(status_code=422, detail=f"could not parse contour KML: {error}")

    result = analyze_catchment(elevation, bbox)

    return CatchmentAnalysisOut(
        pond_location={"lat": result.pond_lat, "lon": result.pond_lon},
        catchment_area_m2=result.catchment_area_m2,
        catchment_area_hectares=result.catchment_area_m2 / 10_000,
        catchment_cell_count=result.catchment_cell_count,
        flow_accumulation_at_pond=result.flow_accumulation_at_pond,
        catchment_boundary=result.catchment_boundary,
        source_bbox=BoundingBoxOut(
            min_lon=bbox.min_lon, min_lat=bbox.min_lat, max_lon=bbox.max_lon, max_lat=bbox.max_lat
        ),
        grid_resolution=DEFAULT_GRID_SIZE,
    )

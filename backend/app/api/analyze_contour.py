from fastapi import APIRouter, HTTPException, UploadFile

from app.domain.catchment import analyze_catchment
from app.infrastructure.kml_parser import DEFAULT_GRID_SIZE, parse_contour_kml
from app.schemas.catchment import BoundingBoxOut, CatchmentAnalysisOut, catchment_fields
from app.services.recommendation import compute_recommendation_fields

router = APIRouter(tags=["analyze-contour"])


@router.post("/analyzeContour", response_model=CatchmentAnalysisOut)
async def analyze_contour(file: UploadFile):
    if not file.filename or not file.filename.lower().endswith((".kml", ".kmz")):
        raise HTTPException(status_code=422, detail="expected a .kml or .kmz file")

    kml_bytes = await file.read()

    try:
        elevation, bbox, kml_lines = parse_contour_kml(kml_bytes)
    except Exception as error:  # noqa: BLE001 -- translating any malformed-upload
        # failure (XML parse errors, bad coordinate values, a corrupted
        # KMZ zip, etc.) into a clean 422 rather than a 500, since this is
        # a user-uploaded file whose failure modes we don't fully control.
        raise HTTPException(status_code=422, detail=f"could not parse contour KML: {error}")

    result = analyze_catchment(elevation, bbox)

    # No "village" for an uploaded survey to hang a rainfall/land lookup off
    # -- use the bbox's own centroid, same idea as reverse-geocoding a click.
    centroid_lat = (bbox.min_lat + bbox.max_lat) / 2
    centroid_lon = (bbox.min_lon + bbox.max_lon) / 2
    recommendation_fields = compute_recommendation_fields(
        centroid_lat, centroid_lon, bbox, result.catchment_area_m2, result.achievable_volume_m3_by_depth
    )

    return CatchmentAnalysisOut(
        **catchment_fields(result).model_dump(),
        **recommendation_fields.model_dump(),
        source_bbox=BoundingBoxOut(
            min_lon=bbox.min_lon, min_lat=bbox.min_lat, max_lon=bbox.max_lon, max_lat=bbox.max_lat
        ),
        grid_resolution=DEFAULT_GRID_SIZE,
        min_elevation=float(elevation.min()),
        max_elevation=float(elevation.max()),
        contours=[
            {"elevation": line.elevation, "coordinates": [[lon, lat] for lon, lat in line.points]}
            for line in kml_lines
        ],
    )

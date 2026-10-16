import logging

from fastapi import APIRouter, HTTPException, UploadFile

from app.core.metrics import timed_analysis, tracer
from app.domain.catchment import analyze_catchment
from app.infrastructure.kml_parser import DEFAULT_GRID_SIZE, parse_contour_kml
from app.schemas.catchment import BoundingBoxOut, CatchmentAnalysisOut, catchment_fields
from app.services.recommendation import compute_recommendation_fields

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analyze-contour"])


@router.post("/analyzeContour", response_model=CatchmentAnalysisOut)
async def analyze_contour(contour_map: UploadFile):
    with timed_analysis("contour") as span:
        # The parameter name IS the multipart form field name FastAPI expects,
        # and "contour_map" is fixed by the submission spec -- renaming this
        # parameter silently changes the public API contract.
        if not contour_map.filename or not contour_map.filename.lower().endswith((".kml", ".kmz")):
            raise HTTPException(status_code=422, detail="expected a .kml or .kmz file")

        kml_bytes = await contour_map.read()

        try:
            with tracer.start_as_current_span("kml.parse") as parse_span:
                parse_span.set_attribute("hydrosage.kml.bytes", len(kml_bytes))
                elevation, bbox, kml_lines, valid_mask = parse_contour_kml(kml_bytes)
                parse_span.set_attribute("hydrosage.kml.contour_lines", len(kml_lines))
        except Exception as error:  # noqa: BLE001 -- translating any malformed-upload
            # failure (XML parse errors, bad coordinate values, a corrupted
            # KMZ zip, etc.) into a clean 422 rather than a 500, since this is
            # a user-uploaded file whose failure modes we don't fully control.
            raise HTTPException(status_code=422, detail=f"could not parse contour KML: {error}")

        with tracer.start_as_current_span("catchment.analyze") as catchment_span:
            catchment_span.set_attribute("hydrosage.grid.cells", int(elevation.size))
            result = analyze_catchment(elevation, bbox, valid_mask=valid_mask)
            catchment_span.set_attribute("hydrosage.catchment.hectares", round(result.catchment_area_m2 / 10_000, 3))

        # No "village" for an uploaded survey to hang a rainfall/land lookup off
        # -- use the bbox's own centroid, same idea as reverse-geocoding a click.
        centroid_lat = (bbox.min_lat + bbox.max_lat) / 2
        centroid_lon = (bbox.min_lon + bbox.max_lon) / 2
        recommendation_fields = compute_recommendation_fields(
            centroid_lat, centroid_lon, bbox, result.catchment_area_m2, result.achievable_volume_m3_by_depth
        )

        span.set_attributes(
            {
                "hydrosage.pond.lat": result.pond_lat,
                "hydrosage.pond.lon": result.pond_lon,
                "hydrosage.catchment.hectares": round(result.catchment_area_m2 / 10_000, 3),
                "hydrosage.runoff.m3_per_year": round(recommendation_fields.runoff_volume_m3 or 0.0, 1),
                "hydrosage.rainfall.source": recommendation_fields.rainfall_source or "none",
            }
        )
        logger.info(
            "contour analysis complete: %s, %.2f ha catchment",
            contour_map.filename,
            result.catchment_area_m2 / 10_000,
            extra={"hydrosage.catchment.hectares": round(result.catchment_area_m2 / 10_000, 3)},
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
                {"elevation": line.elevation, "coordinates": line.points.tolist()}
                for line in kml_lines
            ],
        )

"""Estimates land available for pond excavation within a village's bbox,
by excluding OSM-mapped buildings, water bodies, residential/industrial/
commercial zones, and roads (buffered, since roads are mapped as lines,
not areas) from the bbox area. This is PROJECT_BRIEF.md's own suggested
proxy for "available government land" (ARCHITECTURE.md open question #1)
-- no live government land-record API exists, so OSM coverage stands in.

This is an exclusion-based design deliberately, not an inclusion-based
one: OSM tagging density varies a lot in rural India, so untagged open
land is correctly treated as available by default, rather than requiring
every field to carry a `landuse=farmland` tag it may not actually have.
The trade-off is the opposite direction: anything genuinely unavailable
that isn't mapped in OSM (fenced private land, small unmapped structures,
temples) won't be excluded either. An approximation, not a survey.

Pure function: no I/O -- the actual OSM fetch lives in
infrastructure/land_use_client.py.
"""

import math
from dataclasses import dataclass

from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from app.infrastructure.elevation_client import BoundingBox
from app.infrastructure.land_use_client import ExcludedFeature

METERS_PER_DEGREE_LAT = 111_320.0
# Roads are mapped as lines with zero area -- buffered by a representative
# road-plus-shoulder width so they become an excludable area. Also used as
# a fallback for any area-tagged way missing its closing node.
LINE_BUFFER_M = 5.0


@dataclass(frozen=True)
class LandAvailabilityResult:
    available_area_m2: float
    excluded_feature_count: int


def _degree_area_to_m2(area_deg2: float, mean_lat_deg: float) -> float:
    meters_per_deg_lon = METERS_PER_DEGREE_LAT * math.cos(math.radians(mean_lat_deg))
    return area_deg2 * METERS_PER_DEGREE_LAT * meters_per_deg_lon


def _to_geometry(feature: ExcludedFeature):
    coords = feature.coordinates
    if len(coords) < 2:
        return None

    is_closed = coords[0] == coords[-1]
    if feature.kind == "area" and is_closed and len(coords) >= 4:
        return Polygon(coords)

    buffer_deg = LINE_BUFFER_M / METERS_PER_DEGREE_LAT
    return LineString(coords).buffer(buffer_deg)


def estimate_available_land(
    bbox: BoundingBox, excluded_features: list[ExcludedFeature]
) -> LandAvailabilityResult:
    bbox_polygon = box(bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat)

    geometries = [g for g in (_to_geometry(f) for f in excluded_features) if g is not None and not g.is_empty]
    available_geom = bbox_polygon.difference(unary_union(geometries)) if geometries else bbox_polygon

    mean_lat = (bbox.min_lat + bbox.max_lat) / 2
    available_area_m2 = max(0.0, _degree_area_to_m2(available_geom.area, mean_lat))

    return LandAvailabilityResult(
        available_area_m2=available_area_m2,
        excluded_feature_count=len(excluded_features),
    )

"""Recommends pond depth and surface-area/storage capacity from a target
runoff volume, per PROJECT_BRIEF.md core use case #7. Storage is targeted
to equal the annual runoff volume (domain/runoff.py) -- the pond is sized
to capture a season/year's worth of catchment runoff -- then surface area
is back-solved for a small set of practical depths, matching
ARCHITECTURE.md's "back-calculating surface area within a practical depth
range" rather than a single fixed answer.

Assumes a simple flat-bottomed, square footprint (no side-slope/
trapezoidal correction) -- a documented simplification, not an excavation
design. "Checked against available land" (PROJECT_BRIEF.md) is NOT yet
applied here: land-availability data doesn't exist in this app yet (see
docs/PROJECT_STATUS.md open items). Once it does, the natural extension
is clamping `surface_area_m2` to whatever's actually available at the
site -- same staged-upgrade pattern as domain/runoff.py's coefficient
method being replaced by Curve Number once land-use data exists.

Pure function: no I/O, no FastAPI/DB imports -- testable in isolation,
per docs/ARCHITECTURE.md.
"""

from dataclasses import dataclass

# Standard design depths for small rural storage/percolation ponds under
# Indian watershed-development practice (e.g. MGNREGA farm pond
# guidelines commonly cite 2-4.5m). Offered as a small set of practical
# options rather than one fixed answer, per ARCHITECTURE.md.
CANDIDATE_DEPTHS_M = (2.0, 3.0, 4.0)


@dataclass(frozen=True)
class PondOption:
    depth_m: float
    surface_area_m2: float
    side_length_m: float  # assuming a square footprint


@dataclass(frozen=True)
class PondRecommendation:
    target_storage_m3: float
    options: list[PondOption]


def recommend_pond_dimensions(
    target_storage_m3: float, candidate_depths_m: tuple[float, ...] = CANDIDATE_DEPTHS_M
) -> PondRecommendation:
    if target_storage_m3 < 0:
        raise ValueError("target storage cannot be negative")
    if not candidate_depths_m:
        raise ValueError("need at least one candidate depth")
    if any(depth <= 0 for depth in candidate_depths_m):
        raise ValueError("depths must be positive")

    options = [
        PondOption(
            depth_m=depth,
            surface_area_m2=(area := target_storage_m3 / depth),
            side_length_m=area**0.5,
        )
        for depth in candidate_depths_m
    ]

    return PondRecommendation(target_storage_m3=target_storage_m3, options=options)


def size_pond_from_terrain_capacity(
    achievable_volume_m3_by_depth: dict[float, float],
) -> list[PondOption]:
    """Back-solves a flat square footprint at each candidate depth from
    the site's own real terrain-holding capacity at that depth
    (domain/catchment.py's flood-fill), rather than an aspirational
    demand target. This answers a different question than
    recommend_pond_dimensions above: not "how big must the pond be to
    capture a year's runoff" but "how big can the pond actually be at
    this site" -- the two diverge whenever the catchment is large enough
    that capturing its full annual runoff would mean an unrealistic,
    reservoir-scale pond (see docs/DECISIONS.md D-007). This is the
    app's primary pond-sizing entry point (see services/recommendation.py);
    recommend_pond_dimensions remains available for a target-volume use
    case, but is no longer how the app's own recommendation is sized.
    """
    return [
        PondOption(
            depth_m=depth,
            surface_area_m2=(area := volume / depth),
            side_length_m=area**0.5,
        )
        for depth, volume in sorted(achievable_volume_m3_by_depth.items())
    ]

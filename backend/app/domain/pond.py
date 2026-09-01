"""Two pond-sizing models, per PROJECT_BRIEF.md core use case #7.

`size_pond_options` is the app's primary sizing path (see
services/recommendation.py): each candidate depth's storage volume is bound
to the smaller of two real physical constraints: what the terrain can hold
at that depth (domain/catchment.py's flood-fill) and what the catchment
actually delivers in a year (domain/runoff.py). Sizing to terrain alone
overshoots when the basin is larger than the water available to fill it;
sizing to runoff alone overshoots when the landform cannot hold that much.
The binding bound is whichever is smaller, and it varies by depth -- see
docs/DECISIONS.md D-010 for why. `recommend_pond_dimensions` is the
earlier, demand-driven model (storage targeted to equal one year's estimated
catchment runoff, back-solved into a footprint at a small set of practical
depths); it's kept as an available utility for a target-volume use case,
but is no longer how the app's own recommendation is sized.

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
    volume_m3: float = 0.0  # the storage this footprint holds at this depth


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
            volume_m3=target_storage_m3,
        )
        for depth in candidate_depths_m
    ]

    return PondRecommendation(target_storage_m3=target_storage_m3, options=options)


def size_pond_options(
    achievable_volume_m3_by_depth: dict[float, float],
    annual_runoff_m3: float | None,
) -> list[PondOption]:
    """Back-solves a flat square footprint at each candidate depth from the
    smaller of two real physical bounds:

    * what the terrain can hold at that depth (domain/catchment.py's
      flood-fill over the actual landform), and
    * what the catchment actually delivers in a year (domain/runoff.py).

    Sizing to terrain alone overshoots whenever the basin is larger than
    the water available to fill it -- a pond that would only ever be part
    full is wasted excavation. Sizing to runoff alone overshoots whenever
    the landform cannot hold that much. The binding bound is whichever is
    smaller, and it varies by depth (see docs/DECISIONS.md D-010).

    This is the app's primary pond-sizing entry point (see
    services/recommendation.py); recommend_pond_dimensions remains
    available for a target-volume use case, but is no longer how the
    app's own recommendation is sized.

    Note: surface_area_m2 describes a flat-bottomed square footprint sized to
    hold this depth's bounded volume (the excavation you'd dig), not the
    flood-fill's own traced inundation shape at that depth -- an irregular
    basin's actual water surface at a given depth is generally larger than
    volume/depth would suggest for a flat-bottomed prism.

    volume_m3 on each returned option carries this same bounded volume
    directly, so callers don't need to reconstruct it (lossily) from
    surface_area_m2 * depth_m.

    annual_runoff_m3 of None means the runoff bound is *unknown*, not zero:
    the rainfall service was unreachable. Sizing then falls back to the
    terrain bound alone (the D-007 behaviour), which is the honest answer
    -- the landform's capacity is measured from the uploaded survey and
    doesn't depend on any external service. See docs/DECISIONS.md D-011.
    """
    options = []
    for depth, terrain_capacity_m3 in sorted(achievable_volume_m3_by_depth.items()):
        volume_m3 = terrain_capacity_m3 if annual_runoff_m3 is None else min(terrain_capacity_m3, annual_runoff_m3)
        area = volume_m3 / depth
        options.append(
            PondOption(
                depth_m=depth,
                surface_area_m2=area,
                side_length_m=area**0.5,
                volume_m3=volume_m3,
            )
        )
    return options


def capture_ratio(option: PondOption, annual_runoff_m3: float | None) -> float | None:
    """What share of a typical year's catchment runoff this option holds.

    Returns None when there is no runoff to compare against (zero) or no
    runoff figure at all (None -- the rainfall service was unreachable),
    rather than dividing by zero or by nothing. Reads the option's own
    recorded volume rather than
    reconstructing it from area x depth -- that round-trip is lossy enough
    to return values a hair above 1.0, which would break the documented
    guarantee that a ratio of exactly 1.0 means runoff-limited.
    """
    if annual_runoff_m3 is None or annual_runoff_m3 <= 0:
        return None
    return option.volume_m3 / annual_runoff_m3

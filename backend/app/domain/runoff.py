"""Estimates annual runoff volume from rainfall and catchment area via the
runoff-coefficient method (Rainfall x Area x Coefficient) -- the fallback
PROJECT_BRIEF.md explicitly allows "when land/soil data is unavailable",
which is exactly the current situation: land-use/soil-type data isn't
built yet (see docs/PROJECT_STATUS.md open items). The primary method
ARCHITECTURE.md names, SCS Curve Number, needs a soil hydrologic group and
land-cover classification per cell -- guessing those now would mean an
arbitrary, undocumented CN value, not a real calculation. Upgrading to CN
once land-availability data exists is the natural next step: the
coefficient below gets replaced by land-cover-derived CN values, not
bolted on top of them.

Pure function: no I/O, no FastAPI/DB imports -- testable in isolation,
per docs/ARCHITECTURE.md.
"""

from dataclasses import dataclass

# A single representative value for mixed rural/agricultural terrain under
# monsoon conditions, in line with figures cited in Indian
# watershed-development literature for similar catchments (e.g. the
# Hiware Bazar reference case, docs/DECISIONS.md D-004). This is a
# documented assumption standing in for real site-specific land-use/soil
# data, not a calculated value -- callers should treat `runoff_coefficient`
# on the result as "the assumption used", not "a measured site property".
DEFAULT_RUNOFF_COEFFICIENT = 0.25


@dataclass(frozen=True)
class RunoffResult:
    runoff_volume_m3: float
    runoff_coefficient: float
    method: str  # "runoff_coefficient" for now; "scs_curve_number" once land-use data exists


def estimate_annual_runoff_volume(
    average_annual_rainfall_mm: float,
    catchment_area_m2: float,
    runoff_coefficient: float = DEFAULT_RUNOFF_COEFFICIENT,
) -> RunoffResult:
    if average_annual_rainfall_mm < 0:
        raise ValueError("rainfall cannot be negative")
    if catchment_area_m2 < 0:
        raise ValueError("catchment area cannot be negative")
    if not 0 <= runoff_coefficient <= 1:
        raise ValueError("runoff coefficient must be between 0 and 1")

    rainfall_m = average_annual_rainfall_mm / 1000
    volume_m3 = rainfall_m * catchment_area_m2 * runoff_coefficient

    return RunoffResult(
        runoff_volume_m3=volume_m3,
        runoff_coefficient=runoff_coefficient,
        method="runoff_coefficient",
    )

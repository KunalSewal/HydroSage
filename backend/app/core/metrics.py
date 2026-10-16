"""HydroSage's own OpenTelemetry instruments and tracer.

Generic instrumentation (app/core/telemetry.py) already measures every HTTP
request. These add what only the application knows: how long an analysis
took and how it ended, whether each cache answered, which rainfall source
was used, and how full the analysis queues are -- the questions an operator
of the four-container deployment actually asks (D-015, D-016).

Created through the OpenTelemetry API at import time; they are no-ops until
`setup_telemetry` installs an SDK, and start exporting from then on.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException
from opentelemetry import metrics, trace

tracer = trace.get_tracer("hydrosage")
meter = metrics.get_meter("hydrosage")

analysis_duration = meter.create_histogram(
    "hydrosage.analysis.duration",
    unit="s",
    description="Wall time of one analysis, by input kind and outcome",
)
cache_lookups = meter.create_counter(
    "hydrosage.cache.lookups",
    description="Cache lookups, by cache (dem, catchment, rainfall, land_use) and result (hit, miss)",
)
rainfall_lookups = meter.create_counter(
    "hydrosage.rainfall.lookups",
    description="Rainfall answers, by the source that provided them (open-meteo, nasa-power, none)",
)
analyses_refused = meter.create_counter(
    "hydrosage.analysis.refused",
    description="Analyses refused with 503 because this process was already at its limit",
)


def record_cache(cache: str, hit: bool) -> None:
    result = "hit" if hit else "miss"
    cache_lookups.add(1, {"cache": cache, "result": result})
    trace.get_current_span().set_attribute(f"hydrosage.cache.{cache}", result)


@contextmanager
def timed_analysis(kind: str) -> Iterator[trace.Span]:
    """Wraps one analysis in a span and records its duration and outcome:
    `ok`, `rejected` (a 4xx -- bad input), or `failed` (anything else)."""
    started = time.perf_counter()
    outcome = "ok"
    with tracer.start_as_current_span(f"analysis.{kind}") as span:
        try:
            yield span
        except HTTPException as error:
            outcome = "rejected" if error.status_code < 500 else "failed"
            span.set_attribute("hydrosage.analysis.rejection", str(error.detail))
            raise
        except Exception:
            outcome = "failed"
            raise
        finally:
            span.set_attribute("hydrosage.analysis.outcome", outcome)
            analysis_duration.record(
                time.perf_counter() - started, {"analysis.kind": kind, "analysis.outcome": outcome}
            )

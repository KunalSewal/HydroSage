"""OpenTelemetry instrumentation (app/core/telemetry.py, app/core/metrics.py).

Installs a real SDK with in-memory exporters -- once per test session,
since OpenTelemetry's global providers can only be set once -- then runs
an analysis offline and checks what was recorded.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.api import analyze_area as analyze_area_module
from app.core import telemetry
from app.core.telemetry import redact_url
from app.infrastructure.rainfall_client import DailyRainfall
from app.main import app
from app.services import rainfall_lookup, recommendation

POLYGON = [[81.300, 21.200], [81.320, 21.200], [81.320, 21.220], [81.300, 21.220]]

_spans = InMemorySpanExporter()
_metric_reader = InMemoryMetricReader()


@pytest.fixture(scope="session", autouse=True)
def sdk():
    if not isinstance(trace.get_tracer_provider(), TracerProvider):
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(_spans))
        trace.set_tracer_provider(provider)
        metrics.set_meter_provider(MeterProvider(metric_readers=[_metric_reader]))
    yield


@pytest.fixture(autouse=True)
def clean():
    _spans.clear()
    rainfall_lookup.clear_cache()
    recommendation._land_cache.clear()
    recommendation._land_breaker.reset()
    yield


class _FakeElevationClient:
    def get_dem_for_bbox(self, bbox, demtype="COP30", cache_key=None):
        size = 160
        y, x = np.mgrid[0:size, 0:size]
        return (x + y).astype(np.float64) + 200.0, bbox

    def close(self):
        pass


class _PassThroughCache:
    def get_or_compute(self, key, compute):
        return compute()


class _OpenMeteo:
    def get_daily_rainfall(self, lat, lon, start, end):
        return [DailyRainfall(date="2020-07-01", precipitation_mm=1200.0)]

    def close(self):
        pass


class _NoLandUse:
    def get_excluded_features(self, bbox):
        return []

    def close(self):
        pass


@pytest.fixture
def offline(monkeypatch):
    real_lookup = rainfall_lookup.get_rainfall_summary
    monkeypatch.setattr(analyze_area_module, "ElevationClient", _FakeElevationClient)
    monkeypatch.setattr(
        analyze_area_module.CatchmentCache, "from_settings", classmethod(lambda cls, s: _PassThroughCache())
    )
    monkeypatch.setattr(
        recommendation, "get_rainfall_summary", lambda lat, lon: real_lookup(lat, lon, primary=_OpenMeteo)
    )
    monkeypatch.setattr(recommendation, "LandUseClient", _NoLandUse)


def _by_name():
    return {span.name: span for span in _spans.get_finished_spans()}


def _metric_points(name):
    data = _metric_reader.get_metrics_data()
    points = []
    for resource_metrics in data.resource_metrics if data else []:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == name:
                    points.extend(metric.data.data_points)
    return points


def test_an_area_analysis_is_one_span_tree_with_a_span_per_stage(offline):
    response = TestClient(app).post("/analyzeArea", json={"polygon": POLYGON})
    assert response.status_code == 200

    spans = _by_name()
    root = spans["analysis.area"]
    for stage in ("catchment.analyze", "contours.generate", "recommendation.compute"):
        assert spans[stage].parent.span_id == root.context.span_id, stage
    for lookup in ("rainfall.lookup", "land_use.lookup"):
        assert spans[lookup].parent.span_id == spans["recommendation.compute"].context.span_id, lookup
    assert {s.context.trace_id for s in spans.values()} == {root.context.trace_id}


def test_the_analysis_span_carries_the_domain_result(offline):
    body = TestClient(app).post("/analyzeArea", json={"polygon": POLYGON}).json()

    attributes = _by_name()["analysis.area"].attributes
    assert attributes["hydrosage.analysis.outcome"] == "ok"
    assert attributes["hydrosage.catchment.hectares"] == pytest.approx(body["catchment_area_hectares"], abs=1e-3)
    assert attributes["hydrosage.rainfall.source"] == "open-meteo"
    assert _by_name()["rainfall.lookup"].attributes["hydrosage.cache.rainfall"] == "miss"


def test_a_rejected_area_is_recorded_as_rejected_with_its_reason(offline):
    tiny = [[81.3, 21.2], [81.3003, 21.2], [81.3003, 21.2003], [81.3, 21.2003]]

    TestClient(app).post("/analyzeArea", json={"polygon": tiny})

    attributes = _by_name()["analysis.area"].attributes
    assert attributes["hydrosage.analysis.outcome"] == "rejected"
    assert "too small" in attributes["hydrosage.analysis.rejection"]
    outcomes = {p.attributes["analysis.outcome"] for p in _metric_points("hydrosage.analysis.duration")}
    assert "rejected" in outcomes


def test_cache_lookups_are_counted_as_hits_and_misses(offline):
    client = TestClient(app)
    client.post("/analyzeArea", json={"polygon": POLYGON})
    client.post("/analyzeArea", json={"polygon": POLYGON})  # rainfall and land use now cached

    results = {
        (p.attributes["cache"], p.attributes["result"]): p.value
        for p in _metric_points("hydrosage.cache.lookups")
    }
    assert results.get(("rainfall", "miss"), 0) >= 1
    assert results.get(("rainfall", "hit"), 0) >= 1
    assert results.get(("land_use", "hit"), 0) >= 1


def test_redact_url_hides_api_keys_but_keeps_other_parameters():
    url = "https://portal.opentopography.org/API/globaldem?demtype=COP30&south=21.1&API_Key=abc123secret"

    redacted = redact_url(url)

    assert "abc123secret" not in redacted
    assert "API_Key=REDACTED" in redacted
    assert "demtype=COP30" in redacted and "south=21.1" in redacted


def test_redact_url_leaves_urls_without_a_query_alone():
    assert redact_url("http://127.0.0.1:8101/analyzeArea") == "http://127.0.0.1:8101/analyzeArea"


def test_client_span_hook_overwrites_the_recorded_url():
    class _Request:
        url = "https://portal.opentopography.org/API/globaldem?API_Key=abc123secret"

    with trace.get_tracer("test").start_as_current_span("GET") as span:
        telemetry._redact_client_span(span, _Request())

    recorded = _by_name()["GET"].attributes
    assert "abc123secret" not in recorded["url.full"]
    assert "abc123secret" not in recorded["http.url"]


def test_telemetry_stays_off_without_an_otlp_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.setattr(telemetry, "_configured", False)

    assert telemetry.setup_telemetry("hydrosage-test") is False
    sentinel = object()
    assert telemetry.wrap_asgi(sentinel) is sentinel


def test_secret_url_parameters_are_redacted_from_exported_log_records():
    # httpx logs every request URL at INFO, and OpenTopography's API key is
    # a query parameter -- found in Loki during the first real run.
    import logging

    record = logging.LogRecord(
        "httpx", logging.INFO, __file__, 1,
        'HTTP Request: GET %s "HTTP/1.1 200 OK"',
        ("https://portal.opentopography.org/API/globaldem?south=21.1&API_Key=abc123secret",), None,
    )

    assert telemetry._RedactSecretsFilter().filter(record) is True
    assert "abc123secret" not in record.getMessage()
    assert "API_Key=REDACTED" in record.getMessage()
    assert "south=21.1" in record.getMessage()


def test_httpx_request_logging_is_quietened_when_telemetry_is_on():
    import logging

    telemetry._quiet_noisy_loggers()

    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING


def test_gateway_health_probes_do_not_create_traces():
    # The httpx instrumentation skips a call when HTTP instrumentation is
    # suppressed in the current context; the probes run every 5 s and were
    # otherwise each a separate trace, burying the real requests.
    import asyncio

    import httpx
    from opentelemetry.instrumentation.utils import is_http_instrumentation_enabled

    from app.gateway import create_app

    seen = []

    async def scenario():
        async def handler(request):
            seen.append(is_http_instrumentation_enabled())
            return httpx.Response(200, json={"status": "ok"})

        app = create_app(["http://a:3000", "http://b:3000"], upstream_transport=httpx.MockTransport(handler))
        await app.state.gateway.check_health()

    asyncio.run(scenario())
    assert seen == [False, False]


def test_a_land_use_outage_is_not_retried_on_every_request(monkeypatch):
    # Found from traces: with Overpass down, every analysis spent ~20 s in
    # land_use.lookup on the same timeout and the gateway queue backed up.
    # Remembering failures per area still cost one timeout per new area per
    # instance, every five minutes (seen as clusters of slow traces), so the
    # whole service is now skipped for a while after a failure.
    from app.infrastructure.elevation_client import BoundingBox

    calls = []

    class _DownLandUse:
        def get_excluded_features(self, bbox):
            calls.append(bbox)
            raise TimeoutError("overpass unreachable")

        def close(self):
            pass

    monkeypatch.setattr(recommendation, "LandUseClient", _DownLandUse)
    recommendation._land_breaker.reset()
    first = BoundingBox(min_lon=81.3, min_lat=21.2, max_lon=81.32, max_lat=21.22)
    other_area = BoundingBox(min_lon=37.25, min_lat=-1.53, max_lon=37.26, max_lat=-1.52)

    assert recommendation._get_available_land_hectares(first) is None
    assert recommendation._get_available_land_hectares(first) is None
    assert recommendation._get_available_land_hectares(other_area) is None

    assert len(calls) == 1


def test_the_land_use_breaker_lets_a_call_through_once_its_cooldown_passes(monkeypatch):
    from app.services import recommendation as rec

    now = [1000.0]
    monkeypatch.setattr(rec.time, "monotonic", lambda: now[0])
    breaker = rec._CircuitBreaker(cooldown_seconds=300)

    breaker.record_failure()
    assert breaker.is_open()
    now[0] += 301
    assert not breaker.is_open()

def test_health_probe_access_logs_are_not_exported():
    # The gateway probes every instance every 5 s; their uvicorn access
    # lines were most of the exported log volume and drowned real events.
    import logging

    def access(path):
        return logging.LogRecord(
            "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
            ("127.0.0.1:5000", "GET", path, "1.1", 200), None,
        )

    drop = telemetry._DropHealthProbeAccessLogs()
    assert drop.filter(access("/health")) is False
    assert drop.filter(access("/analyzeArea")) is True

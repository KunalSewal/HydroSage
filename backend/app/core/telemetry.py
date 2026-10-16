"""OpenTelemetry setup: traces, metrics and logs, exported over OTLP/HTTP.

Opt-in. Nothing is configured unless OTEL_EXPORTER_OTLP_ENDPOINT is set
(e.g. http://localhost:4318, an OpenTelemetry Collector), so the 512 MB lab
containers pay no memory for the SDK unless telemetry is wanted. See
docs/DECISIONS.md D-016 and docs/OBSERVABILITY.md.

The rest of the code depends only on the OpenTelemetry *API*
(`trace.get_tracer`, `metrics.get_meter`, plain `logging`). Until
`setup_telemetry` installs an SDK those calls are no-ops; afterwards the
same tracers, instruments and loggers start exporting. That is why custom
spans and metrics can sit in modules that are imported before setup runs.

What one call gives a process:
- traces: a server span per HTTP request (FastAPI or plain ASGI), a client
  span per outgoing httpx call -- with W3C `traceparent` propagated, so a
  request is one trace across gateway -> API instance -> external APIs --
  plus the custom spans in the analysis pipeline;
- metrics: HTTP server/client durations, process CPU and memory, and the
  custom `hydrosage.*` instruments (app/core/metrics.py), every 10 s;
- logs: every log record at INFO and above, carrying the trace and span id
  of the request that emitted it.
"""

import logging
import os
import re
import socket
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from opentelemetry import metrics, trace

logger = logging.getLogger(__name__)

# Paths whose requests would only add noise: the gateway probes /health on
# every backend every 5 s, and /gateway/status is an operator's page.
EXCLUDED_URLS = "health,gateway/status"
METRIC_EXPORT_INTERVAL_MS = 10_000

_configured = False

# Query parameters whose values must never leave the process in a span.
# OpenTopography takes its API key as `API_Key=...` in the URL, and the
# httpx instrumentation records the full URL of every outgoing call.
_SECRET_PARAM = re.compile(r"key|token|secret|password|signature", re.IGNORECASE)


def redact_url(url: str) -> str:
    """`url` with the value of every secret-looking query parameter
    replaced by REDACTED."""
    parts = urlsplit(url)
    if not parts.query:
        return url
    query = [(k, "REDACTED" if _SECRET_PARAM.search(k) else v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit(parts._replace(query=urlencode(query)))


# The same parameters, wherever they appear inside free text such as a log
# message: `API_Key=abc` -> `API_Key=REDACTED`.
_SECRET_IN_TEXT = re.compile(r"([?&][^=&\s\"']*(?:key|token|secret|password|signature)[^=&\s\"']*=)[^&\s\"']+", re.IGNORECASE)


class _RedactSecretsFilter(logging.Filter):
    """Redacts secret query parameters in every record the OTLP handler
    exports. Defence in depth: the first real run sent two httpx request
    lines carrying OpenTopography's API key to Loki (D-016)."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = _SECRET_IN_TEXT.sub(lambda m: m.group(1) + "REDACTED", message)
        if redacted != message:
            record.msg, record.args = redacted, ()
        return True


class _DropHealthProbeAccessLogs(logging.Filter):
    """Drops uvicorn's access-log line for each /health probe. The gateway
    probes every instance every 5 s; those lines were most of the exported
    log volume and buried real events. The probes are excluded from traces
    for the same reason (EXCLUDED_URLS)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "uvicorn.access" or not isinstance(record.args, tuple) or len(record.args) < 3:
            return True
        return not str(record.args[2]).startswith("/health")


def _quiet_noisy_loggers() -> None:
    """httpx and httpcore log every request at INFO -- full URLs included --
    which, once the root logger is at INFO for export, means one log line
    per health probe and per external call. Their spans already carry that
    information, redacted."""
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


def _redact_client_span(span, request) -> None:
    """httpx request hook: overwrite the recorded URL with a redacted one
    (both the current and the older semantic-convention attribute)."""
    if span is None or not span.is_recording():
        return
    url = redact_url(str(request.url))
    span.set_attribute("url.full", url)
    span.set_attribute("http.url", url)


def telemetry_enabled() -> bool:
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"))


def setup_telemetry(service_name: str, extra_log_loggers: tuple[str, ...] = ()) -> bool:
    """Configures the SDK for this process if telemetry is enabled; True
    if it did. Safe to call more than once (only the first call acts).

    `service_name` is the default for the `service.name` resource
    attribute; OTEL_SERVICE_NAME overrides it, and OTEL_SERVICE_INSTANCE_ID
    distinguishes several instances of one service (the demo script sets
    it per API port).

    `extra_log_loggers` names loggers that don't propagate to the root
    logger (uvicorn's access log, analyze_only's memory log) but should
    still be exported.
    """
    global _configured
    if _configured or not telemetry_enabled():
        return False

    # Imported here, not at module level, so a process with telemetry off
    # never loads the SDK, exporters or protobuf.
    from opentelemetry import _logs
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create(
        {
            "service.name": os.environ.get("OTEL_SERVICE_NAME", service_name),
            "service.namespace": "hydrosage",
            "service.instance.id": os.environ.get(
                "OTEL_SERVICE_INSTANCE_ID", f"{socket.gethostname()}:{os.getpid()}"
            ),
            "deployment.environment": os.environ.get("HYDROSAGE_ENVIRONMENT", "local"),
        }
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(OTLPMetricExporter(), export_interval_millis=METRIC_EXPORT_INTERVAL_MS)
        ],
    )
    metrics.set_meter_provider(meter_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    _logs.set_logger_provider(logger_provider)
    handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    handler.addFilter(_RedactSecretsFilter())
    handler.addFilter(_DropHealthProbeAccessLogs())
    _quiet_noisy_loggers()
    root = logging.getLogger()
    root.addHandler(handler)
    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)
    for name in extra_log_loggers:
        logging.getLogger(name).addHandler(handler)

    # Every outgoing httpx call -- to OpenTopography, Open-Meteo, NASA POWER,
    # Overpass, Nominatim, and the gateway's calls to API instances --
    # becomes a client span, and carries `traceparent` to the next hop.
    HTTPXClientInstrumentor().instrument(request_hook=_redact_client_span)
    # CPU and memory of this process: the numbers that matter on a 512 MB
    # container (D-012).
    SystemMetricsInstrumentor(
        config={
            "process.cpu.utilization": None,
            "process.memory.usage": None,
            "process.thread.count": None,
        }
    ).instrument()

    _configured = True
    logger.info("OpenTelemetry enabled for %s, exporting to %s", resource.attributes["service.name"],
                os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"])
    return True


def instrument_fastapi(app) -> None:
    """A server span and HTTP server metrics per request. No-op when
    telemetry is off."""
    if not _configured:
        return
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app, excluded_urls=EXCLUDED_URLS, exclude_spans=["receive", "send"])


def wrap_asgi(app):
    """The same, for a plain ASGI app (the Starlette gateway). Returns the
    app unchanged when telemetry is off."""
    if not _configured:
        return app
    from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

    return OpenTelemetryMiddleware(app, excluded_urls=EXCLUDED_URLS, exclude_spans=["receive", "send"])

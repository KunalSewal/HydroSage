# Observability with OpenTelemetry

HydroSage exports **traces, metrics and logs** over OTLP when
`OTEL_EXPORTER_OTLP_ENDPOINT` is set, and does nothing otherwise. Design and
rationale: `docs/DECISIONS.md` D-016.

## Run it locally

Needs Docker Desktop running.

```powershell
.\deploy\demo_local.ps1 -Telemetry
```

This starts `grafana/otel-lgtm` (OpenTelemetry Collector + Tempo + Prometheus +
Loki + Grafana) from `deploy/observability/`, loads the HydroSage dashboard,
and starts the gateway and two analysis instances exporting to it. Then:

| What | Where |
|---|---|
| The app | http://localhost:8080 |
| HydroSage dashboard (metrics) | http://localhost:3000/d/hydrosage |
| Traces | Grafana → Explore → **Tempo** → Search, service `hydrosage-gateway` |
| Logs | Grafana → Explore → **Loki** → `{service_name=~"hydrosage.*"}` |
| Raw metrics | Grafana → Explore → **Prometheus** → e.g. `hydrosage_cache_lookups_total` |

Stop with `.\deploy\demo_local.ps1 -Stop`; stop the stack with
`docker compose -f deploy/observability/docker-compose.yml down` (this also
deletes its data).

## Enabling it anywhere else

Set these for each process (the demo script does this per process):

```
OTEL_EXPORTER_OTLP_ENDPOINT=http://<collector-host>:4318
OTEL_SERVICE_NAME=hydrosage-api            # or hydrosage-gateway
OTEL_SERVICE_INSTANCE_ID=api1              # distinguishes instances
```

## What is collected

**Traces.** A server span per HTTP request at the gateway and at each instance;
a client span per outgoing httpx call, with W3C `traceparent` propagated, so one
user request is one trace across gateway → instance → OpenTopography /
Open-Meteo / NASA POWER / Overpass / Nominatim. Custom spans per stage:

| Span | Where | Key attributes |
|---|---|---|
| `gateway.dispatch` | gateway | queue wait, chosen instance, attempts, outcome |
| `analysis.area` / `analysis.contour` | instance | outcome, area, catchment ha, pond lat/lon, runoff m³/yr, rainfall source |
| `dem.fetch` | instance | cache hit/miss, bytes, grid shape |
| `kml.parse` | instance | bytes, contour lines |
| `catchment.analyze` | instance | grid cells, catchment ha, cache hit/miss |
| `contours.generate` | instance | lines |
| `recommendation.compute` → `rainfall.lookup`, `land_use.lookup` | instance | source, mm/yr, cache hit/miss, available land |

**Metrics** (every 10 s): HTTP server and client durations; process CPU, memory
and threads; and HydroSage's own:

| Metric | Meaning |
|---|---|
| `hydrosage.analysis.duration` | analysis wall time, by kind and outcome (ok / rejected / failed) |
| `hydrosage.cache.lookups` | by cache (dem, catchment, rainfall, land_use) and result (hit / miss) |
| `hydrosage.rainfall.lookups` | by source (open-meteo, nasa-power, none) |
| `hydrosage.analysis.in_flight`, `.waiting`, `.refused` | per-instance gate load and refusals |
| `hydrosage.gateway.queued`, `.queue_wait`, `.dispatches` | gateway queue depth, wait time, outcomes |
| `hydrosage.gateway.backend.in_flight`, `.healthy` | the gateway's view of each instance |

**Logs.** Every record at INFO and above, with `trace_id` and `span_id`, so a log
line in Loki links to its trace in Tempo. Secret-looking URL parameters (the
OpenTopography API key) are redacted from spans and logs before export.

"""Load balancer and static frontend server for the four-container deploy.

Runs in its own 512 MB container in front of N API instances (each running
app.analyze_only). It serves the built frontend from the same origin as the
API, so the browser needs no CORS, and forwards API calls to the instances:

- Analyses (POST /analyzeArea, /analyzeContour) go to a healthy instance
  with a free slot, and never more than `per_backend_limit`
  (default 1) at once per instance: one analysis peaks at 305-500 MB against
  a 512 MB cap, so a second concurrent one is an OOM kill (D-012, D-013).
  Among free instances the choice is by rendezvous hashing of the request,
  so a repeated area lands on the instance whose disk cache already holds
  its DEM (saving a ~15 s download and an OpenTopography quota call), while
  different areas still spread evenly. Requests beyond capacity wait in a
  bounded FIFO queue; once the queue is full
  they are refused at once with 503 + Retry-After instead of piling up.
- Light calls (GET /geocode, the OpenAPI docs) go to any healthy instance
  without taking an analysis slot.
- An instance that refuses a connection is marked down and the request is
  retried on another; a background health check (GET /health every few
  seconds) brings it back once it answers. Instances restart themselves to
  shed memory (analyze_only.py's recycle), so brief outages are routine.

Deliberately imports nothing from the analysis stack -- see
tests/test_gateway.py. Configured from the environment; see
docs/DEPLOYMENT.md:

    GATEWAY_BACKENDS=http://10.1.75.53:3267,http://10.1.75.53:3268 \\
    GATEWAY_STATIC_DIR=/home/student/frontend-dist \\
    uvicorn app.gateway:app --host 0.0.0.0 --port 3000
"""

import asyncio
import contextlib
import hashlib
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

logger = logging.getLogger("hydrosage.gateway")

ANALYSIS_PATHS = ("/analyzeArea", "/analyzeContour")
LIGHT_PATHS = ("/geocode", "/docs", "/openapi.json")

# Headers that describe one hop's connection, not the message, and so must
# not be copied between the client and upstream connections.
_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
    "trailers", "transfer-encoding", "upgrade", "host", "content-length",
}


@dataclass
class Backend:
    url: str
    healthy: bool = True  # optimistic until the first check says otherwise
    in_flight: int = 0
    served: int = 0
    failures: int = 0
    last_error: str | None = None

    @property
    def label(self) -> str:
        return urlsplit(self.url).netloc


@dataclass
class Gateway:
    backends: list[Backend]
    client: httpx.AsyncClient
    per_backend_limit: int = 1
    max_queue: int = 20
    queue_timeout: float = 120.0
    max_body_bytes: int = 25 * 1024 * 1024
    _waiters: deque = field(default_factory=deque)
    refused: int = 0

    # ---- choosing a backend -------------------------------------------------

    def _free_backend(self, exclude: set[str], affinity_key: bytes) -> Backend | None:
        candidates = [
            b for b in self.backends
            if b.healthy and b.in_flight < self.per_backend_limit and b.url not in exclude
        ]
        if not candidates:
            return None
        # Fewest in flight first (matters when per_backend_limit > 1), then
        # rendezvous hashing: each (request, backend) pair gets a stable
        # score and the highest wins, so the same request keeps going to the
        # same backend while it's free, and a backend leaving or joining only
        # moves the requests that were mapped to it.
        return min(
            candidates,
            key=lambda b: (b.in_flight, -int.from_bytes(hashlib.sha1(affinity_key + b.url.encode()).digest()[:8])),
        )

    async def _claim_slot(self, exclude: set[str], affinity_key: bytes) -> Backend | None:
        """A backend with a free analysis slot, reserved for the caller; waits
        in FIFO order for one. None if the queue is full or the wait times out."""
        backend = self._free_backend(exclude, affinity_key) if not self._waiters else None
        if backend is not None:
            backend.in_flight += 1
            return backend

        if len(self._waiters) >= self.max_queue:
            return None
        if not any(b.healthy and b.url not in exclude for b in self.backends):
            return None  # nothing could free up for this waiter; don't make it wait

        waiter: asyncio.Future = asyncio.get_running_loop().create_future()
        entry = (waiter, exclude, affinity_key)
        self._waiters.append(entry)
        try:
            return await asyncio.wait_for(waiter, self.queue_timeout)
        except TimeoutError:
            return None
        finally:
            with contextlib.suppress(ValueError):
                self._waiters.remove(entry)

    def _release_slot(self, backend: Backend) -> None:
        backend.in_flight -= 1
        self._hand_off_free_slots()

    def _hand_off_free_slots(self) -> None:
        """Gives freed (or newly healthy) capacity to the oldest waiters."""
        for waiter, exclude, affinity_key in list(self._waiters):
            if waiter.done():
                continue
            backend = self._free_backend(exclude, affinity_key)
            if backend is None:
                continue
            backend.in_flight += 1
            waiter.set_result(backend)

    # ---- forwarding ---------------------------------------------------------

    async def _send(self, backend: Backend, request: Request, body: bytes) -> httpx.Response:
        headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP}
        return await self.client.request(
            request.method,
            backend.url + request.url.path,
            params=request.query_params,
            headers=headers,
            content=body,
        )

    def _mark_down(self, backend: Backend, error: Exception) -> None:
        backend.healthy = False
        backend.failures += 1
        backend.last_error = f"{type(error).__name__}: {error}"
        logger.warning("backend %s marked down: %s", backend.url, backend.last_error)

    @staticmethod
    def _relay(upstream: httpx.Response, backend: Backend, started: float) -> Response:
        headers = {k: v for k, v in upstream.headers.items() if k.lower() not in _HOP_BY_HOP}
        headers.pop("content-encoding", None)  # httpx has already decoded the body
        headers["x-served-by"] = backend.label
        headers["x-gateway-time-ms"] = f"{(time.perf_counter() - started) * 1000:.0f}"
        return Response(upstream.content, status_code=upstream.status_code, headers=headers)

    async def forward_analysis(self, request: Request) -> Response:
        started = time.perf_counter()
        body = await request.body()
        if len(body) > self.max_body_bytes:
            return JSONResponse({"detail": "upload too large"}, status_code=413)

        tried: set[str] = set()
        while len(tried) < len(self.backends):
            backend = await self._claim_slot(exclude=tried, affinity_key=request.url.path.encode() + body)
            if backend is None:
                if tried and not any(b.healthy for b in self.backends):
                    break  # every backend just refused; say so rather than "busy"
                self.refused += 1
                return JSONResponse(
                    {"detail": "all analysis servers are busy; please retry shortly"},
                    status_code=503,
                    headers={"Retry-After": "15"},
                )
            try:
                upstream = await self._send(backend, request, body)
            except (httpx.ConnectError, httpx.ConnectTimeout) as error:
                # Never reached the backend, so the analysis didn't start --
                # safe to try the next one.
                self._mark_down(backend, error)
                tried.add(backend.url)
                continue
            except httpx.HTTPError as error:
                self._mark_down(backend, error)
                return JSONResponse({"detail": f"analysis server failed: {error}"}, status_code=502)
            finally:
                self._release_slot(backend)
            backend.served += 1
            return self._relay(upstream, backend, started)

        return JSONResponse({"detail": "no analysis server is reachable"}, status_code=502)

    async def forward_light(self, request: Request) -> Response:
        started = time.perf_counter()
        body = await request.body()
        candidates = sorted(
            (b for b in self.backends if b.healthy), key=lambda b: (b.in_flight, b.served)
        ) or list(self.backends)
        for backend in candidates:
            try:
                upstream = await self._send(backend, request, body)
            except (httpx.ConnectError, httpx.ConnectTimeout) as error:
                self._mark_down(backend, error)
                continue
            except httpx.HTTPError as error:
                return JSONResponse({"detail": f"upstream failed: {error}"}, status_code=502)
            return self._relay(upstream, backend, started)
        return JSONResponse({"detail": "no API server is reachable"}, status_code=502)

    # ---- health -------------------------------------------------------------

    async def check_health(self) -> None:
        async def probe(backend: Backend) -> None:
            try:
                response = await self.client.get(backend.url + "/health", timeout=5.0)
                ok = response.status_code == 200
            except (httpx.ConnectError, httpx.ConnectTimeout) as error:
                ok = False
                backend.last_error = f"{type(error).__name__}: {error}"
            except httpx.HTTPError:
                # Connected but answered slowly: a backend mid-analysis is
                # CPU-bound and can miss the timeout while perfectly alive.
                # Busy is not down -- leave its state as it was.
                return
            if ok and not backend.healthy:
                logger.warning("backend %s is healthy again", backend.url)
            if ok:
                backend.last_error = None
            backend.healthy = ok

        await asyncio.gather(*(probe(b) for b in self.backends))
        self._hand_off_free_slots()

    def status(self) -> dict:
        return {
            "status": "ok" if any(b.healthy for b in self.backends) else "degraded",
            "queued": len(self._waiters),
            "refused_total": self.refused,
            "per_backend_limit": self.per_backend_limit,
            "max_queue": self.max_queue,
            "backends": [
                {
                    "url": b.url,
                    "healthy": b.healthy,
                    "in_flight": b.in_flight,
                    "served": b.served,
                    "failures": b.failures,
                    "last_error": b.last_error,
                }
                for b in self.backends
            ],
        }


def create_app(
    backend_urls: list[str],
    *,
    upstream_transport: httpx.AsyncBaseTransport | None = None,
    static_dir: Path | None = None,
    per_backend_limit: int = 1,
    max_queue: int = 20,
    queue_timeout: float = 120.0,
    upstream_timeout: float = 180.0,
    health_interval: float = 5.0,
    max_body_bytes: int = 25 * 1024 * 1024,
) -> Starlette:
    if not backend_urls:
        raise ValueError("the gateway needs at least one backend URL")

    gateway = Gateway(
        backends=[Backend(url.rstrip("/")) for url in backend_urls],
        client=httpx.AsyncClient(transport=upstream_transport, timeout=upstream_timeout),
        per_backend_limit=per_backend_limit,
        max_queue=max_queue,
        queue_timeout=queue_timeout,
        max_body_bytes=max_body_bytes,
    )

    async def status(request: Request) -> JSONResponse:
        return JSONResponse(gateway.status())

    routes = [
        Route("/health", status),
        Route("/gateway/status", status),
        *(Route(path, gateway.forward_analysis, methods=["POST"]) for path in ANALYSIS_PATHS),
        *(Route(path, gateway.forward_light, methods=["GET"]) for path in LIGHT_PATHS),
    ]
    if static_dir is not None and static_dir.is_dir():
        routes.append(Mount("/", StaticFiles(directory=static_dir, html=True)))

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        async def health_loop() -> None:
            while True:
                await gateway.check_health()
                await asyncio.sleep(health_interval)

        task = asyncio.create_task(health_loop())
        try:
            yield
        finally:
            task.cancel()
            await gateway.client.aclose()

    app = Starlette(routes=routes, lifespan=lifespan)
    app.state.gateway = gateway
    return app


def _app_from_env() -> Starlette | None:
    backends = [u.strip() for u in os.environ.get("GATEWAY_BACKENDS", "").split(",") if u.strip()]
    if not backends:
        return None  # imported for tests/tools; `uvicorn app.gateway:app` needs GATEWAY_BACKENDS
    static = os.environ.get("GATEWAY_STATIC_DIR")
    return create_app(
        backends,
        static_dir=Path(static) if static else None,
        per_backend_limit=int(os.environ.get("GATEWAY_PER_BACKEND_LIMIT", "1")),
        max_queue=int(os.environ.get("GATEWAY_MAX_QUEUE", "20")),
        queue_timeout=float(os.environ.get("GATEWAY_QUEUE_TIMEOUT", "120")),
    )


app = _app_from_env()

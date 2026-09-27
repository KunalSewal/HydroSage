import asyncio
import sys

import httpx

from app.gateway import create_app


def _backend_handler(delays: dict[str, float] | None = None, down: set[str] | None = None, log: list | None = None):
    """A fake fleet of API instances behind one MockTransport, keyed by host."""
    delays = delays or {}
    down = down or set()

    async def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host in down:
            raise httpx.ConnectError("connection refused", request=request)
        if log is not None:
            log.append((host, request.url.path))
        await asyncio.sleep(delays.get(host, 0))
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(200, json={"served_by": host, "path": request.url.path})

    return handler


def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway")


def run(coro):
    return asyncio.run(coro)


def test_proxies_an_analysis_to_a_backend_and_says_which():
    async def scenario():
        app = create_app(["http://a:3000"], upstream_transport=httpx.MockTransport(_backend_handler()))
        async with _client(app) as client:
            response = await client.post("/analyzeArea", json={"polygon": []})
        assert response.status_code == 200
        assert response.json() == {"served_by": "a", "path": "/analyzeArea"}
        assert response.headers["x-served-by"] == "a:3000"

    run(scenario())


def test_spreads_concurrent_analyses_across_backends():
    async def scenario():
        transport = httpx.MockTransport(_backend_handler(delays={"a": 0.2, "b": 0.2}))
        app = create_app(["http://a:3000", "http://b:3000"], upstream_transport=transport)
        async with _client(app) as client:
            responses = await asyncio.gather(
                client.post("/analyzeArea", json={}), client.post("/analyzeArea", json={})
            )
        assert sorted(r.json()["served_by"] for r in responses) == ["a", "b"]

    run(scenario())


def test_never_sends_a_backend_more_than_one_analysis_at_a_time():
    async def scenario():
        in_flight = {"n": 0, "max": 0}

        async def handler(request):
            in_flight["n"] += 1
            in_flight["max"] = max(in_flight["max"], in_flight["n"])
            await asyncio.sleep(0.05)
            in_flight["n"] -= 1
            return httpx.Response(200, json={})

        app = create_app(["http://a:3000"], upstream_transport=httpx.MockTransport(handler), max_queue=10)
        async with _client(app) as client:
            responses = await asyncio.gather(*(client.post("/analyzeArea", json={}) for _ in range(4)))
        assert all(r.status_code == 200 for r in responses)
        assert in_flight["max"] == 1  # queued, not stacked onto the 512 MB instance

    run(scenario())


def test_refuses_with_503_once_the_queue_is_full():
    async def scenario():
        transport = httpx.MockTransport(_backend_handler(delays={"a": 0.3}))
        app = create_app(["http://a:3000"], upstream_transport=transport, max_queue=1)
        async with _client(app) as client:
            responses = await asyncio.gather(*(client.post("/analyzeArea", json={}) for _ in range(3)))
        statuses = sorted(r.status_code for r in responses)
        assert statuses == [200, 200, 503]
        refused = next(r for r in responses if r.status_code == 503)
        assert "retry-after" in refused.headers

    run(scenario())


def test_retries_on_another_backend_when_one_refuses_connections():
    async def scenario():
        transport = httpx.MockTransport(_backend_handler(down={"a"}))
        app = create_app(["http://a:3000", "http://b:3000"], upstream_transport=transport)
        async with _client(app) as client:
            # Varied requests, so affinity routing tries "a" for at least one.
            responses = [await client.post("/analyzeArea", json={"n": i}) for i in range(6)]
            status = (await client.get("/gateway/status")).json()
        assert all(r.status_code == 200 and r.json()["served_by"] == "b" for r in responses)
        health = {b["url"]: b["healthy"] for b in status["backends"]}
        assert health == {"http://a:3000": False, "http://b:3000": True}

    run(scenario())


def test_answers_502_when_every_backend_is_down():
    async def scenario():
        transport = httpx.MockTransport(_backend_handler(down={"a", "b"}))
        app = create_app(["http://a:3000", "http://b:3000"], upstream_transport=transport)
        async with _client(app) as client:
            response = await client.post("/analyzeArea", json={})
        assert response.status_code == 502

    run(scenario())


def test_place_search_is_proxied_without_taking_an_analysis_slot():
    async def scenario():
        log = []
        transport = httpx.MockTransport(_backend_handler(delays={"a": 0.2}, log=log))
        app = create_app(["http://a:3000"], upstream_transport=transport, max_queue=0)
        async with _client(app) as client:
            analysis = asyncio.create_task(client.post("/analyzeArea", json={}))
            await asyncio.sleep(0.05)
            search = await client.get("/geocode", params={"query": "Durg"})
            await analysis
        assert search.status_code == 200
        assert ("a", "/geocode") in log

    run(scenario())


def test_health_check_marks_a_recovered_backend_healthy_again():
    async def scenario():
        down = {"a"}
        transport = httpx.MockTransport(_backend_handler(down=down))
        app = create_app(["http://a:3000"], upstream_transport=transport)
        gateway = app.state.gateway
        await gateway.check_health()
        assert not gateway.backends[0].healthy
        down.clear()
        await gateway.check_health()
        assert gateway.backends[0].healthy

    run(scenario())


def test_serves_the_built_frontend(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>HydroSage</title>")

    async def scenario():
        app = create_app(["http://a:3000"], upstream_transport=httpx.MockTransport(_backend_handler()), static_dir=tmp_path)
        async with _client(app) as client:
            response = await client.get("/")
        assert response.status_code == 200
        assert "HydroSage" in response.text

    run(scenario())


def test_rejects_oversized_uploads_before_forwarding():
    async def scenario():
        log = []
        transport = httpx.MockTransport(_backend_handler(log=log))
        app = create_app(["http://a:3000"], upstream_transport=transport, max_body_bytes=10)
        async with _client(app) as client:
            response = await client.post("/analyzeContour", content=b"x" * 11)
        assert response.status_code == 413
        assert log == []

    run(scenario())


def test_stays_light_by_not_importing_the_analysis_stack():
    # The gateway runs in its own 512 MB container and must not pull in
    # pysheds/rasterio/scipy (~320 MB of imports, D-012). Checked in a
    # fresh interpreter, since this test run has already imported them.
    import subprocess

    probe = "import sys, app.gateway; print(sorted(m for m in ('pysheds', 'rasterio', 'scipy', 'numpy') if m in sys.modules))"
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "[]"


def test_fails_fast_instead_of_queueing_when_no_backend_is_healthy():
    async def scenario():
        transport = httpx.MockTransport(_backend_handler(down={"a"}))
        app = create_app(["http://a:3000"], upstream_transport=transport, queue_timeout=30)
        app.state.gateway.backends[0].healthy = False
        loop = asyncio.get_running_loop()
        async with _client(app) as client:
            started = loop.time()
            response = await client.post("/analyzeArea", json={})
        assert response.status_code == 503
        assert loop.time() - started < 1.0

    run(scenario())


def test_repeats_of_the_same_request_go_to_the_same_backend_when_it_is_free():
    # Each instance caches DEMs on its own disk; routing a repeated area to
    # the instance that already fetched it saves a ~15 s download and one
    # call from OpenTopography's 50-per-day quota.
    async def scenario():
        transport = httpx.MockTransport(_backend_handler())
        app = create_app(["http://a:3000", "http://b:3000", "http://c:3000"], upstream_transport=transport)
        async with _client(app) as client:
            servers = set()
            for _ in range(4):
                response = await client.post("/analyzeArea", json={"polygon": [[1, 2], [3, 4], [5, 6]]})
                servers.add(response.json()["served_by"])
        assert len(servers) == 1

    run(scenario())


def test_different_requests_still_spread_across_backends():
    async def scenario():
        transport = httpx.MockTransport(_backend_handler())
        app = create_app(["http://a:3000", "http://b:3000"], upstream_transport=transport)
        async with _client(app) as client:
            servers = set()
            for i in range(12):
                response = await client.post("/analyzeArea", json={"polygon": [[i, 0], [i, 1], [i + 1, 1]]})
                servers.add(response.json()["served_by"])
        assert servers == {"a", "b"}

    run(scenario())


def test_a_slow_health_answer_does_not_mark_a_busy_backend_down():
    # A backend mid-analysis is CPU-bound and can answer /health late. That
    # is "busy", not "down": marking it down refused requests with 503 while
    # the queue still had room (found by the single-instance load test).
    async def scenario():
        async def handler(request):
            raise httpx.ReadTimeout("slow", request=request)

        app = create_app(["http://a:3000"], upstream_transport=httpx.MockTransport(handler))
        gateway = app.state.gateway
        await gateway.check_health()
        assert gateway.backends[0].healthy

    run(scenario())

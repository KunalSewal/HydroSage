"""The slim deployment entrypoint (app/analyze_only.py): what the four lab
containers actually run."""

from fastapi.testclient import TestClient

from app import analyze_only


def test_health_reports_gate_load():
    body = TestClient(analyze_only.app).get("/health").json()

    assert body == {"status": "ok", "in_flight": 0, "waiting": 0}


def test_serves_place_search_route():
    # Mounted so the map's search box works against a database-free deploy.
    paths = set(analyze_only.app.openapi()["paths"])
    assert {"/analyzeContour", "/analyzeArea", "/geocode"} <= paths


def test_refuses_an_analysis_with_503_when_the_gate_is_full(monkeypatch):
    async def always_full(timeout):
        return False

    monkeypatch.setattr(analyze_only._gate, "acquire", always_full)

    response = TestClient(analyze_only.app).post("/analyzeArea", json={"polygon": [[0, 0], [1, 0], [1, 1]]})

    assert response.status_code == 503
    assert response.headers["retry-after"] == "10"

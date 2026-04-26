"""Health endpoint contract."""
from fastapi.testclient import TestClient

from repopulse.main import app


def test_healthz_returns_ok() -> None:
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "RepoPulse"
    assert "version" in body


def test_healthz_includes_environment() -> None:
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.json()["environment"] == "development"

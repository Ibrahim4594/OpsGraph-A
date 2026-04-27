"""Health endpoint contract."""
import pytest
from fastapi.testclient import TestClient

from repopulse.main import app, create_app


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


def test_healthz_includes_agentic_enabled_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for M4 C1: the dashboard StatusBar reads kill-switch
    state from this field. Re-reading per request matches ADR-003 §3."""
    monkeypatch.setenv("REPOPULSE_AGENTIC_ENABLED", "false")
    app2 = create_app()
    with TestClient(app2) as c:
        body = c.get("/healthz").json()
    assert body["agentic_enabled"] is False


def test_healthz_agentic_enabled_default_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REPOPULSE_AGENTIC_ENABLED", raising=False)
    app2 = create_app()
    with TestClient(app2) as c:
        body = c.get("/healthz").json()
    assert body["agentic_enabled"] is True

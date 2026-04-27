"""POST /api/v1/events ingest endpoint contract."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from repopulse.main import create_app


@pytest.fixture
def client() -> TestClient:
    """TestClient that returns 500 on unhandled errors instead of re-raising,
    so the simulate-error path can be asserted as an HTTP response."""
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


def _valid_envelope() -> dict[str, object]:
    return {
        "event_id": str(uuid4()),
        "source": "github",
        "kind": "push",
        "payload": {"ref": "refs/heads/main", "commits": 3},
    }


def test_post_event_returns_202_with_event_id(client: TestClient) -> None:
    envelope = _valid_envelope()
    r = client.post("/api/v1/events", json=envelope)
    assert r.status_code == 202
    body = r.json()
    assert body["accepted"] is True
    assert body["event_id"] == envelope["event_id"]


def test_post_event_missing_event_id_returns_422(client: TestClient) -> None:
    envelope = _valid_envelope()
    del envelope["event_id"]
    r = client.post("/api/v1/events", json=envelope)
    assert r.status_code == 422


def test_post_event_missing_source_returns_422(client: TestClient) -> None:
    envelope = _valid_envelope()
    del envelope["source"]
    r = client.post("/api/v1/events", json=envelope)
    assert r.status_code == 422


def test_post_event_invalid_event_id_returns_422(client: TestClient) -> None:
    envelope = _valid_envelope()
    envelope["event_id"] = "not-a-uuid"
    r = client.post("/api/v1/events", json=envelope)
    assert r.status_code == 422


def test_post_event_simulate_error_returns_500(client: TestClient) -> None:
    envelope = _valid_envelope()
    envelope["simulate_error"] = True
    r = client.post("/api/v1/events", json=envelope)
    assert r.status_code == 500


def test_post_event_simulate_error_default_false(client: TestClient) -> None:
    envelope = _valid_envelope()
    r = client.post("/api/v1/events", json=envelope)
    assert r.status_code == 202


def test_post_event_forwards_to_orchestrator() -> None:
    """A successful POST must reach app.state.orchestrator. Without this wiring,
    the recommendations endpoint can never produce non-empty output from real HTTP
    traffic — regression guard for the M3 review C1 finding."""
    from repopulse.main import create_app
    from repopulse.pipeline.orchestrator import PipelineOrchestrator

    orch = PipelineOrchestrator()
    app = create_app(orchestrator=orch)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.post("/api/v1/events", json=_valid_envelope())
        assert r.status_code == 202
    assert orch.snapshot()["events"] == 1

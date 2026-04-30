"""POST /api/v1/events ingest endpoint contract."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from repopulse.api.events import _MAX_PAYLOAD_BYTES
from repopulse.main import create_app
from repopulse.testing import make_inmem_orchestrator

# Matches conftest autouse ``REPOPULSE_API_SHARED_SECRET``.
PIPELINE_API_HEADERS = {"Authorization": "Bearer test-pipeline-api-secret"}


@pytest.fixture
def client() -> TestClient:
    """TestClient that returns 500 on unhandled errors instead of re-raising,
    so the simulate-error path can be asserted as an HTTP response."""
    orch, _ = make_inmem_orchestrator()
    app = create_app(orchestrator=orch)
    return TestClient(app, raise_server_exceptions=False)


def _valid_envelope() -> dict[str, object]:
    return {
        "event_id": str(uuid4()),
        "source": "github",
        "kind": "push",
        "payload": {"ref": "refs/heads/main", "commits": 3},
    }


def test_post_event_requires_auth(client: TestClient) -> None:
    r = client.post("/api/v1/events", json=_valid_envelope())
    assert r.status_code == 401


def test_post_event_returns_202_with_event_id(client: TestClient) -> None:
    envelope = _valid_envelope()
    r = client.post("/api/v1/events", json=envelope, headers=PIPELINE_API_HEADERS)
    assert r.status_code == 202
    body = r.json()
    assert body["accepted"] is True
    assert body["event_id"] == envelope["event_id"]
    assert body["duplicate"] is False


def test_post_event_duplicate_returns_202_with_duplicate_true() -> None:
    """T6 idempotency contract: same event_id POSTed twice is NOT a 409.

    Both responses are 202; the second carries ``duplicate: true`` so a
    well-behaved client can log the retry without treating it as failure.
    See ``docs/ingest-idempotency.md`` for the full rationale.
    """
    orch, state = make_inmem_orchestrator()
    app = create_app(orchestrator=orch)
    envelope = _valid_envelope()
    with TestClient(app, raise_server_exceptions=False) as c:
        r1 = c.post("/api/v1/events", json=envelope, headers=PIPELINE_API_HEADERS)
        r2 = c.post("/api/v1/events", json=envelope, headers=PIPELINE_API_HEADERS)
    assert r1.status_code == 202
    assert r1.json()["duplicate"] is False
    assert r2.status_code == 202
    assert r2.json()["duplicate"] is True
    # Persistence side-effects: only ONE raw_events row.
    assert len(state.raw_events) == 1


def test_post_event_missing_event_id_returns_422(client: TestClient) -> None:
    envelope = _valid_envelope()
    del envelope["event_id"]
    r = client.post("/api/v1/events", json=envelope, headers=PIPELINE_API_HEADERS)
    assert r.status_code == 422


def test_post_event_missing_source_returns_422(client: TestClient) -> None:
    envelope = _valid_envelope()
    del envelope["source"]
    r = client.post("/api/v1/events", json=envelope, headers=PIPELINE_API_HEADERS)
    assert r.status_code == 422


def test_post_event_invalid_event_id_returns_422(client: TestClient) -> None:
    envelope = _valid_envelope()
    envelope["event_id"] = "not-a-uuid"
    r = client.post("/api/v1/events", json=envelope, headers=PIPELINE_API_HEADERS)
    assert r.status_code == 422


def test_post_event_simulate_error_returns_403_when_not_allowed(
    client: TestClient,
) -> None:
    envelope = _valid_envelope()
    envelope["simulate_error"] = True
    r = client.post("/api/v1/events", json=envelope, headers=PIPELINE_API_HEADERS)
    assert r.status_code == 403


def test_post_event_simulate_error_returns_500_when_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPOPULSE_ALLOW_SIMULATE_ERROR", "true")
    orch, _ = make_inmem_orchestrator()
    app = create_app(orchestrator=orch)
    with TestClient(app, raise_server_exceptions=False) as c:
        envelope = _valid_envelope()
        envelope["simulate_error"] = True
        r = c.post("/api/v1/events", json=envelope, headers=PIPELINE_API_HEADERS)
    assert r.status_code == 500


def test_post_event_simulate_error_default_false(client: TestClient) -> None:
    envelope = _valid_envelope()
    r = client.post("/api/v1/events", json=envelope, headers=PIPELINE_API_HEADERS)
    assert r.status_code == 202


def test_post_event_forwards_to_orchestrator() -> None:
    """A successful POST must reach app.state.orchestrator."""
    orch, state = make_inmem_orchestrator()
    app = create_app(orchestrator=orch)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.post(
            "/api/v1/events",
            json=_valid_envelope(),
            headers=PIPELINE_API_HEADERS,
        )
        assert r.status_code == 202
    assert len(state.raw_events) == 1
    assert len(state.normalized_events) == 1


def test_post_event_rejects_oversized_payload_json(client: TestClient) -> None:
    """P2: cap serialized payload size (GitHub-style bounded ingest)."""
    huge = {"blob": "x" * (_MAX_PAYLOAD_BYTES + 512)}
    envelope = {
        "event_id": str(uuid4()),
        "source": "github",
        "kind": "push",
        "payload": huge,
    }
    r = client.post("/api/v1/events", json=envelope, headers=PIPELINE_API_HEADERS)
    assert r.status_code == 422


def test_post_event_503_when_api_secret_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REPOPULSE_API_SHARED_SECRET", raising=False)
    orch, _ = make_inmem_orchestrator()
    app = create_app(orchestrator=orch)
    with TestClient(app) as c:
        r = c.post(
            "/api/v1/events",
            json=_valid_envelope(),
            headers=PIPELINE_API_HEADERS,
        )
    assert r.status_code == 503

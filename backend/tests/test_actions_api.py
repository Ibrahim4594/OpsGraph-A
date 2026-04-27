"""Tests for GET /api/v1/actions."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.main import create_app
from repopulse.pipeline.orchestrator import PipelineOrchestrator

_T0 = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)


def _envelope(*, source: str = "github") -> EventEnvelope:
    return EventEnvelope.model_validate(
        {"event_id": uuid4(), "source": source, "kind": "push", "payload": {}}
    )


def _seed_pending(orch: PipelineOrchestrator) -> str:
    orch.ingest(_envelope(source="github"), received_at=_T0)
    orch.record_anomalies(
        [
            Anomaly(
                timestamp=_T0 + timedelta(seconds=10),
                value=11.5, baseline_median=10.0, baseline_mad=1.0,
                score=5.0, severity="warning", series_name="otel-metrics",
            ),
            Anomaly(
                timestamp=_T0 + timedelta(seconds=20),
                value=11.5, baseline_median=10.0, baseline_mad=1.0,
                score=5.0, severity="warning", series_name="otel-metrics",
            ),
        ]
    )
    orch.evaluate(window_seconds=300.0)
    return str(orch.latest_recommendations(limit=1)[0].recommendation_id)


def test_actions_endpoint_empty_returns_count_zero() -> None:
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/v1/actions")
    assert r.status_code == 200
    assert r.json() == {"actions": [], "count": 0}


def test_actions_endpoint_returns_history_after_approve() -> None:
    orch = PipelineOrchestrator()
    rec_id = _seed_pending(orch)
    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        client.post(
            f"/api/v1/recommendations/{rec_id}/approve",
            json={"operator": "alice"},
        )
        r = client.get("/api/v1/actions")
    body = r.json()
    assert body["count"] >= 1
    first = body["actions"][0]
    assert first["kind"] == "approve"
    assert first["actor"] == "alice"
    assert first["recommendation_id"] == rec_id
    assert "at" in first


def test_actions_endpoint_includes_observe_entries() -> None:
    """When R1 fires, the orchestrator records a system-observe entry."""
    orch = PipelineOrchestrator()
    orch.ingest(_envelope(source="github"), received_at=_T0)
    orch.evaluate(window_seconds=300.0)
    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        body = client.get("/api/v1/actions").json()
    kinds = [entry["kind"] for entry in body["actions"]]
    actors = [entry["actor"] for entry in body["actions"]]
    assert "observe" in kinds
    assert "system" in actors


def test_actions_endpoint_respects_limit_zero() -> None:
    orch = PipelineOrchestrator()
    _seed_pending(orch)
    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        r = client.get("/api/v1/actions?limit=0")
    assert r.json() == {"actions": [], "count": 0}

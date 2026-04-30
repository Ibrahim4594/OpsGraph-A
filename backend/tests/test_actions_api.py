"""Tests for GET /api/v1/actions."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.main import create_app
from repopulse.pipeline.async_orchestrator import PipelineOrchestrator
from repopulse.testing import make_inmem_orchestrator

_T0 = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)

_AUTH = {"Authorization": "Bearer test-pipeline-api-secret"}


def _envelope(*, source: str = "github") -> EventEnvelope:
    return EventEnvelope.model_validate(
        {"event_id": uuid4(), "source": source, "kind": "push", "payload": {}}
    )


async def _seed_pending(orch: PipelineOrchestrator) -> str:
    await orch.ingest(_envelope(source="github"), received_at=_T0)
    await orch.record_anomalies(
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
    await orch.evaluate(window_seconds=300.0)
    recs = await orch.latest_recommendations(limit=1)
    return str(recs[0].recommendation_id)


def test_actions_endpoint_empty_returns_count_zero() -> None:
    orch, _ = make_inmem_orchestrator()
    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        r = client.get("/api/v1/actions", headers=_AUTH)
    assert r.status_code == 200
    assert r.json() == {"actions": [], "count": 0}


async def test_actions_endpoint_returns_history_after_approve() -> None:
    orch, _ = make_inmem_orchestrator()
    rec_id = await _seed_pending(orch)
    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        client.post(
            f"/api/v1/recommendations/{rec_id}/approve",
            headers=_AUTH,
        )
        r = client.get("/api/v1/actions", headers=_AUTH)
    body = r.json()
    assert body["count"] >= 1
    first = body["actions"][0]
    assert first["kind"] == "approve"
    assert first["actor"] == "authenticated-api"
    assert first["recommendation_id"] == rec_id
    assert "at" in first


async def test_actions_endpoint_includes_observe_entries() -> None:
    """When R1 fires, the orchestrator records a system-observe entry."""
    orch, _ = make_inmem_orchestrator()
    await orch.ingest(_envelope(source="github"), received_at=_T0)
    await orch.evaluate(window_seconds=300.0)
    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        body = client.get("/api/v1/actions", headers=_AUTH).json()
    kinds = [entry["kind"] for entry in body["actions"]]
    actors = [entry["actor"] for entry in body["actions"]]
    assert "observe" in kinds
    assert "system" in actors


async def test_actions_endpoint_respects_limit_zero() -> None:
    orch, _ = make_inmem_orchestrator()
    await _seed_pending(orch)
    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        r = client.get("/api/v1/actions?limit=0", headers=_AUTH)
    assert r.json() == {"actions": [], "count": 0}


def test_actions_endpoint_includes_workflow_run_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for M4 C2: the /usage endpoint records a
    ``kind='workflow-run'`` ActionHistoryEntry per ADR-004 §3 so the
    dashboard's workflow-run filter chip is not dead."""
    monkeypatch.setenv("REPOPULSE_AGENTIC_ENABLED", "true")
    monkeypatch.setenv("REPOPULSE_AGENTIC_SHARED_SECRET", "test-secret")
    orch, _ = make_inmem_orchestrator()
    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        client.post(
            "/api/v1/github/usage",
            json={
                "workflow_name": "agentic-issue-triage",
                "run_id": 12345,
                "duration_seconds": 18.4,
                "conclusion": "success",
                "repository": "x/y",
                "runner": "linux",
            },
            headers={"Authorization": "Bearer test-secret"},
        )
        body = client.get("/api/v1/actions", headers=_AUTH).json()
    kinds = [entry["kind"] for entry in body["actions"]]
    actors = [entry["actor"] for entry in body["actions"]]
    assert "workflow-run" in kinds
    assert "agentic-issue-triage" in actors

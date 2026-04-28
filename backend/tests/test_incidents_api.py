"""Tests for GET /api/v1/incidents."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.main import create_app
from repopulse.pipeline.orchestrator import PipelineOrchestrator

_T0 = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)

_AUTH = {"Authorization": "Bearer test-pipeline-api-secret"}


@pytest.fixture
def populated_orchestrator() -> PipelineOrchestrator:
    orch = PipelineOrchestrator()
    orch.ingest(
        EventEnvelope.model_validate(
            {
                "event_id": uuid4(),
                "source": "github",
                "kind": "push",
                "payload": {"occurred_at": _T0.isoformat()},
            }
        ),
        received_at=_T0,
    )
    orch.record_anomalies(
        [
            Anomaly(
                timestamp=_T0,
                value=200.0,
                baseline_median=10.0,
                baseline_mad=1.0,
                score=20.0,
                severity="critical",
                series_name="otel-metrics",
            )
        ]
    )
    orch.evaluate()
    return orch


def test_incidents_endpoint_returns_empty_when_orchestrator_empty() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/v1/incidents", headers=_AUTH)
    assert response.status_code == 200
    assert response.json() == {"incidents": [], "count": 0}


def test_incidents_endpoint_returns_orchestrator_incidents(
    populated_orchestrator: PipelineOrchestrator,
) -> None:
    app = create_app(orchestrator=populated_orchestrator)
    with TestClient(app) as client:
        response = client.get("/api/v1/incidents", headers=_AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    incident = body["incidents"][0]
    assert "incident_id" in incident
    assert sorted(incident["sources"]) == ["github", "otel-metrics"]
    assert incident["anomaly_count"] == 1
    assert incident["event_count"] == 1
    assert "started_at" in incident
    assert "ended_at" in incident


def test_incidents_endpoint_respects_limit_zero(
    populated_orchestrator: PipelineOrchestrator,
) -> None:
    app = create_app(orchestrator=populated_orchestrator)
    with TestClient(app) as client:
        response = client.get("/api/v1/incidents?limit=0", headers=_AUTH)
    assert response.json() == {"incidents": [], "count": 0}


def test_incidents_endpoint_rejects_negative_limit() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/v1/incidents?limit=-1", headers=_AUTH)
    assert response.status_code == 422

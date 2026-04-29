"""GET /api/v1/recommendations contract."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.main import create_app
from repopulse.pipeline.async_orchestrator import PipelineOrchestrator
from tests._inmem_orchestrator import make_inmem_orchestrator

_T0 = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)

_AUTH = {"Authorization": "Bearer test-pipeline-api-secret"}


def _envelope(*, source: str = "github") -> EventEnvelope:
    return EventEnvelope.model_validate(
        {"event_id": uuid4(), "source": source, "kind": "push", "payload": {}}
    )


def _anomaly(*, at: datetime, source: str = "otel-metrics", severity: str = "critical") -> Anomaly:
    return Anomaly(
        timestamp=at,
        value=200.0,
        baseline_median=10.0,
        baseline_mad=1.0,
        score=20.0,
        severity=severity,  # type: ignore[arg-type]
        series_name=source,
    )


def test_recommendations_endpoint_empty_list_returns_200_count_zero() -> None:
    orch, _ = make_inmem_orchestrator()
    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        r = client.get("/api/v1/recommendations", headers=_AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body == {"recommendations": [], "count": 0}


async def test_recommendations_endpoint_returns_orchestrator_output() -> None:
    orch, _ = make_inmem_orchestrator()
    await orch.ingest(_envelope(source="github"), received_at=_T0)
    await orch.record_anomalies(
        [_anomaly(at=_T0 + timedelta(seconds=30), source="otel-metrics")]
    )
    await orch.evaluate(window_seconds=300.0)

    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        r = client.get("/api/v1/recommendations", headers=_AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 1
        rec = body["recommendations"][0]
        assert rec["action_category"] in {"observe", "triage", "escalate", "rollback"}
        assert 0.0 <= rec["confidence"] <= 1.0
        assert rec["risk_level"] in {"low", "medium", "high"}
        assert isinstance(rec["evidence_trace"], list)
        assert "incident_id" in rec
        assert "recommendation_id" in rec


async def test_recommendations_endpoint_respects_limit_query_param() -> None:
    orch, _ = make_inmem_orchestrator()
    for i in range(5):
        await orch.ingest(_envelope(), received_at=_T0 + timedelta(hours=i))
        await orch.record_anomalies([_anomaly(at=_T0 + timedelta(hours=i, seconds=10))])
        await orch.evaluate()

    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        r = client.get("/api/v1/recommendations?limit=2", headers=_AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 2
        assert len(body["recommendations"]) == 2


async def test_recommendations_endpoint_default_limit_caps_at_ten() -> None:
    """The route serves at most ``limit`` rows (default 10) regardless of
    how many incidents have been correlated. v2.0 dropped the bounded
    in-memory deque cap; the API-side ``limit`` is the only ceiling."""
    orch, _ = make_inmem_orchestrator()
    for i in range(15):
        await orch.ingest(_envelope(), received_at=_T0 + timedelta(hours=i))
        await orch.record_anomalies([_anomaly(at=_T0 + timedelta(hours=i, seconds=10))])
        await orch.evaluate()

    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        r = client.get("/api/v1/recommendations", headers=_AUTH)
        body = r.json()
        assert body["count"] == 10


# --- M4: state field serialized + approval transitions ---


async def _seed_pending_recommendation(orch: PipelineOrchestrator) -> str:
    """Drives the orchestrator to emit one pending (R3) recommendation,
    returns its UUID."""
    await orch.ingest(_envelope(source="github"), received_at=_T0)
    await orch.record_anomalies(
        [
            _anomaly(at=_T0 + timedelta(seconds=10), severity="warning"),
            _anomaly(at=_T0 + timedelta(seconds=20), severity="warning"),
        ]
    )
    await orch.evaluate(window_seconds=300.0)
    recs = await orch.latest_recommendations(limit=1)
    rec = recs[0]
    assert rec.state == "pending"
    return str(rec.recommendation_id)


async def test_recommendations_endpoint_serializes_state_field() -> None:
    orch, _ = make_inmem_orchestrator()
    await _seed_pending_recommendation(orch)
    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        body = client.get("/api/v1/recommendations", headers=_AUTH).json()
    assert body["recommendations"][0]["state"] == "pending"


async def test_approve_pending_recommendation_transitions_to_approved() -> None:
    orch, _ = make_inmem_orchestrator()
    rec_id = await _seed_pending_recommendation(orch)
    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        r = client.post(
            f"/api/v1/recommendations/{rec_id}/approve",
            headers=_AUTH,
        )
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "approved"
    assert body["actor"] == "authenticated-api"
    assert body["recommendation_id"] == rec_id


async def test_reject_pending_recommendation_with_reason() -> None:
    orch, _ = make_inmem_orchestrator()
    rec_id = await _seed_pending_recommendation(orch)
    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        r = client.post(
            f"/api/v1/recommendations/{rec_id}/reject",
            headers=_AUTH,
            json={"reason": "false positive"},
        )
    assert r.status_code == 200
    assert r.json()["state"] == "rejected"


async def test_double_approve_returns_409() -> None:
    orch, _ = make_inmem_orchestrator()
    rec_id = await _seed_pending_recommendation(orch)
    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        client.post(
            f"/api/v1/recommendations/{rec_id}/approve",
            headers=_AUTH,
        )
        r = client.post(
            f"/api/v1/recommendations/{rec_id}/approve",
            headers=_AUTH,
        )
    assert r.status_code == 409


async def test_approve_unknown_id_returns_404() -> None:
    orch, _ = make_inmem_orchestrator()
    await _seed_pending_recommendation(orch)  # populate but skip its id
    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        r = client.post(
            "/api/v1/recommendations/00000000-0000-0000-0000-000000000000/approve",
            headers=_AUTH,
        )
    assert r.status_code == 404


async def test_approve_observed_recommendation_returns_409() -> None:
    """R1 emits state='observed'; further transitions are not allowed."""
    orch, _ = make_inmem_orchestrator()
    await orch.ingest(_envelope(source="github"), received_at=_T0)
    await orch.evaluate(window_seconds=300.0)  # no anomalies → R1 → observed
    recs = await orch.latest_recommendations(limit=1)
    rec = recs[0]
    assert rec.state == "observed"

    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        r = client.post(
            f"/api/v1/recommendations/{rec.recommendation_id}/approve",
            headers=_AUTH,
        )
    assert r.status_code == 409


async def test_approve_writes_action_history_entry() -> None:
    orch, _ = make_inmem_orchestrator()
    rec_id = await _seed_pending_recommendation(orch)
    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        client.post(
            f"/api/v1/recommendations/{rec_id}/approve",
            headers=_AUTH,
        )
    history = await orch.latest_actions(limit=10)
    assert any(
        entry.kind == "approve"
        and entry.actor == "authenticated-api"
        and str(entry.recommendation_id) == rec_id
        for entry in history
    )

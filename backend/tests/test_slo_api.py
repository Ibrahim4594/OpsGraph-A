"""Tests for GET /api/v1/slo."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from repopulse.api.events import EventEnvelope
from repopulse.main import create_app
from repopulse.pipeline.async_orchestrator import PipelineOrchestrator
from tests._inmem_orchestrator import make_inmem_orchestrator

_T0 = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)

_AUTH = {"Authorization": "Bearer test-pipeline-api-secret"}


def _envelope(*, source: str, kind: str, severity: str | None = None) -> EventEnvelope:
    payload: dict[str, object] = {"occurred_at": _T0.isoformat()}
    if severity is not None:
        payload["severity"] = severity
    return EventEnvelope.model_validate(
        {
            "event_id": uuid4(),
            "source": source,
            "kind": kind,
            "payload": payload,
        }
    )


async def _seed_events(
    orch: PipelineOrchestrator,
    *,
    successes: int,
    errors: int,
) -> None:
    for i in range(successes):
        await orch.ingest(
            _envelope(source="github", kind="push"),
            received_at=_T0 + timedelta(seconds=i),
        )
    for i in range(errors):
        await orch.ingest(
            _envelope(source="otel-logs", kind="error-log", severity="error"),
            received_at=_T0 + timedelta(seconds=successes + i),
        )


def test_slo_endpoint_no_traffic_returns_perfect_availability() -> None:
    orch, _ = make_inmem_orchestrator()
    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        body = client.get("/api/v1/slo", headers=_AUTH).json()
    assert body["service"] == "RepoPulse"
    assert body["total_events"] == 0
    assert body["error_events"] == 0
    assert body["availability"] == 1.0
    assert body["burn_band"] == "ok"


async def test_slo_endpoint_computes_availability_from_event_log() -> None:
    """100 events with 2 error-log entries → 0.98 availability,
    0.99 default target → over-budget (burn=2.0) → ``slow`` band per
    Google SRE multi-window alert semantics (page at 6×, slow at 1×)."""
    orch, _ = make_inmem_orchestrator()
    await _seed_events(orch, successes=98, errors=2)
    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        body = client.get("/api/v1/slo", headers=_AUTH).json()
    assert body["total_events"] == 100
    assert body["error_events"] == 2
    assert abs(body["availability"] - 0.98) < 1e-9
    assert body["target"] == 0.99
    assert body["burn_rate"] > 1.0
    assert body["burn_band"] == "slow"


async def test_slo_endpoint_fast_burn_band_when_burn_exceeds_threshold() -> None:
    """50 errors out of 100 → burn ≈ 50× → fast band (>= 14.4)."""
    orch, _ = make_inmem_orchestrator()
    await _seed_events(orch, successes=50, errors=50)
    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        body = client.get("/api/v1/slo", headers=_AUTH).json()
    assert body["burn_band"] == "fast"


async def test_slo_endpoint_within_target_reports_ok_band() -> None:
    orch, _ = make_inmem_orchestrator()
    await _seed_events(orch, successes=100, errors=0)
    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        body = client.get("/api/v1/slo", headers=_AUTH).json()
    assert body["error_events"] == 0
    assert body["availability"] == 1.0
    assert body["burn_band"] == "ok"


async def test_slo_endpoint_target_is_overridable_via_query() -> None:
    """An optional ``?target=0.95`` query lets the dashboard preview
    different target settings without redeploy."""
    orch, _ = make_inmem_orchestrator()
    await _seed_events(orch, successes=98, errors=2)
    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        body = client.get("/api/v1/slo?target=0.95", headers=_AUTH).json()
    assert body["target"] == 0.95
    # 0.98 ≥ 0.95, so within target
    assert body["burn_band"] == "ok"

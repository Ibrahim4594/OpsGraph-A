"""Async :class:`PipelineOrchestrator` glue contract (in-memory fakes).

Legacy bounded-deque tests were removed in T11: the in-memory helper uses
unbounded dicts; retention is a DB / ops concern (M3.2).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.pipeline.normalize import NormalizedEvent
from repopulse.recommend.engine import Recommendation
from repopulse.testing import make_inmem_orchestrator

_T0 = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


def _envelope(
    *,
    source: str = "github",
    kind: str = "push",
    payload: dict[str, object] | None = None,
) -> EventEnvelope:
    return EventEnvelope.model_validate(
        {
            "event_id": uuid4(),
            "source": source,
            "kind": kind,
            "payload": payload or {},
        }
    )


def _anomaly(
    *, at: datetime, source: str = "otel-metrics", severity: str = "critical"
) -> Anomaly:
    return Anomaly(
        timestamp=at,
        value=200.0,
        baseline_median=10.0,
        baseline_mad=1.0,
        score=20.0,
        severity=severity,  # type: ignore[arg-type]
        series_name=source,
    )


@pytest.mark.asyncio
async def test_orchestrator_ingest_returns_normalized_event() -> None:
    orch, _ = make_inmem_orchestrator()
    env = _envelope()
    n = await orch.ingest(env, received_at=_T0)
    assert n is not None
    assert isinstance(n, NormalizedEvent)
    assert n.event_id == env.event_id


@pytest.mark.asyncio
async def test_orchestrator_snapshot_reflects_counts() -> None:
    orch, _ = make_inmem_orchestrator()
    snap = await orch.snapshot()
    assert snap == {"events": 0, "anomalies": 0, "incidents": 0, "recommendations": 0}
    await orch.ingest(_envelope(), received_at=_T0)
    await orch.ingest(_envelope(), received_at=_T0 + timedelta(seconds=10))
    await orch.record_anomalies([_anomaly(at=_T0)])
    snap = await orch.snapshot()
    assert snap["events"] == 2
    assert snap["anomalies"] == 1


@pytest.mark.asyncio
async def test_orchestrator_evaluate_with_no_input_returns_empty() -> None:
    orch, _ = make_inmem_orchestrator()
    new_recs = await orch.evaluate()
    assert new_recs == []


@pytest.mark.asyncio
async def test_orchestrator_evaluate_creates_recommendations_per_incident() -> None:
    orch, _ = make_inmem_orchestrator()
    await orch.ingest(_envelope(source="github"), received_at=_T0)
    await orch.record_anomalies(
        [_anomaly(at=_T0 + timedelta(seconds=30), source="otel-metrics")]
    )
    new_recs = await orch.evaluate(window_seconds=300.0)
    assert len(new_recs) == 1
    assert all(isinstance(r, Recommendation) for r in new_recs)


@pytest.mark.asyncio
async def test_orchestrator_latest_recommendations_returns_newest_first() -> None:
    orch, _ = make_inmem_orchestrator()
    await orch.ingest(_envelope(source="github"), received_at=_T0)
    await orch.record_anomalies([_anomaly(at=_T0 + timedelta(seconds=30))])
    await orch.evaluate()
    later = _T0 + timedelta(hours=1)
    await orch.ingest(_envelope(source="github"), received_at=later)
    await orch.record_anomalies([_anomaly(at=later + timedelta(seconds=10))])
    await orch.evaluate()
    recs = await orch.latest_recommendations(limit=10)
    assert len(recs) >= 2
    assert (await orch.snapshot())["recommendations"] == len(recs)


@pytest.mark.asyncio
async def test_orchestrator_latest_recommendations_respects_limit() -> None:
    orch, _ = make_inmem_orchestrator()
    for i in range(5):
        await orch.ingest(_envelope(source="github"), received_at=_T0 + timedelta(hours=i))
        await orch.record_anomalies(
            [_anomaly(at=_T0 + timedelta(hours=i, seconds=10))]
        )
        await orch.evaluate()
    recs = await orch.latest_recommendations(limit=3)
    assert len(recs) == 3


@pytest.mark.asyncio
async def test_orchestrator_evaluate_twice_with_no_new_data_does_not_duplicate() -> None:
    """Idempotence: second evaluate with same data yields no new recommendations."""
    orch, _ = make_inmem_orchestrator()
    await orch.ingest(_envelope(source="github"), received_at=_T0)
    await orch.record_anomalies([_anomaly(at=_T0 + timedelta(seconds=30))])

    first = await orch.evaluate(window_seconds=300.0)
    second = await orch.evaluate(window_seconds=300.0)

    assert len(first) == 1
    assert second == []
    assert (await orch.snapshot())["recommendations"] == 1


@pytest.mark.asyncio
async def test_orchestrator_evaluate_picks_up_only_genuinely_new_incidents() -> None:
    orch, _ = make_inmem_orchestrator()
    await orch.ingest(_envelope(source="github"), received_at=_T0)
    await orch.record_anomalies([_anomaly(at=_T0 + timedelta(seconds=30))])
    first = await orch.evaluate(window_seconds=300.0)
    assert len(first) == 1

    later = _T0 + timedelta(hours=2)
    await orch.ingest(_envelope(source="github"), received_at=later)
    await orch.record_anomalies([_anomaly(at=later + timedelta(seconds=30))])
    second = await orch.evaluate(window_seconds=300.0)
    assert len(second) == 1
    assert second[0].recommendation_id != first[0].recommendation_id


@pytest.mark.asyncio
async def test_orchestrator_record_normalized_appends_event_directly() -> None:
    """``record_normalized`` persists a pre-built NormalizedEvent (usage path)."""
    orch, _ = make_inmem_orchestrator()
    event = NormalizedEvent(
        event_id=uuid4(),
        received_at=_T0,
        occurred_at=_T0,
        source="agentic-workflow",
        kind="workflow-failure",
        severity="warning",
        attributes={"workflow.name": "ci"},
    )
    await orch.record_normalized(event)
    assert (await orch.snapshot())["events"] == 1

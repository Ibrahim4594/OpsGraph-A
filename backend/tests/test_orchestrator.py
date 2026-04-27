"""PipelineOrchestrator: in-memory glue contract."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.pipeline.normalize import NormalizedEvent
from repopulse.pipeline.orchestrator import PipelineOrchestrator
from repopulse.recommend.engine import Recommendation

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


def test_orchestrator_ingest_returns_normalized_event() -> None:
    orch = PipelineOrchestrator()
    env = _envelope()
    n = orch.ingest(env, received_at=_T0)
    assert isinstance(n, NormalizedEvent)
    assert n.event_id == env.event_id


def test_orchestrator_snapshot_reflects_counts() -> None:
    orch = PipelineOrchestrator()
    snap = orch.snapshot()
    assert snap == {"events": 0, "anomalies": 0, "incidents": 0, "recommendations": 0}
    orch.ingest(_envelope(), received_at=_T0)
    orch.ingest(_envelope(), received_at=_T0 + timedelta(seconds=10))
    orch.record_anomalies([_anomaly(at=_T0)])
    snap = orch.snapshot()
    assert snap["events"] == 2
    assert snap["anomalies"] == 1


def test_orchestrator_evaluate_with_no_input_returns_empty() -> None:
    orch = PipelineOrchestrator()
    new_recs = orch.evaluate()
    assert new_recs == []


def test_orchestrator_evaluate_creates_recommendations_per_incident() -> None:
    orch = PipelineOrchestrator()
    orch.ingest(_envelope(source="github"), received_at=_T0)
    orch.record_anomalies([_anomaly(at=_T0 + timedelta(seconds=30), source="otel-metrics")])
    new_recs = orch.evaluate(window_seconds=300.0)
    assert len(new_recs) == 1
    assert all(isinstance(r, Recommendation) for r in new_recs)


def test_orchestrator_latest_recommendations_returns_newest_first() -> None:
    orch = PipelineOrchestrator()
    orch.ingest(_envelope(source="github"), received_at=_T0)
    orch.record_anomalies([_anomaly(at=_T0 + timedelta(seconds=30))])
    orch.evaluate()
    # Trigger a second batch from a separate, later incident
    later = _T0 + timedelta(hours=1)
    orch.ingest(_envelope(source="github"), received_at=later)
    orch.record_anomalies([_anomaly(at=later + timedelta(seconds=10))])
    orch.evaluate()
    recs = orch.latest_recommendations(limit=10)
    assert len(recs) >= 2
    # Newest first: the second batch's recommendation_id should appear before the first
    assert orch.snapshot()["recommendations"] == len(recs)


def test_orchestrator_latest_recommendations_respects_limit() -> None:
    orch = PipelineOrchestrator()
    for i in range(5):
        orch.ingest(_envelope(source="github"), received_at=_T0 + timedelta(hours=i))
        orch.record_anomalies([_anomaly(at=_T0 + timedelta(hours=i, seconds=10))])
        orch.evaluate()
    recs = orch.latest_recommendations(limit=3)
    assert len(recs) == 3


def test_orchestrator_bounded_deque_drops_oldest_events() -> None:
    orch = PipelineOrchestrator(max_events=3)
    for i in range(10):
        orch.ingest(_envelope(source="github"), received_at=_T0 + timedelta(seconds=i))
    assert orch.snapshot()["events"] == 3


def test_orchestrator_bounded_deque_drops_oldest_recommendations() -> None:
    orch = PipelineOrchestrator(max_recommendations=2)
    for i in range(5):
        orch.ingest(_envelope(source="github"), received_at=_T0 + timedelta(hours=i))
        orch.record_anomalies([_anomaly(at=_T0 + timedelta(hours=i, seconds=10))])
        orch.evaluate()
    assert orch.snapshot()["recommendations"] == 2


def test_orchestrator_evaluate_twice_with_no_new_data_does_not_duplicate() -> None:
    """Idempotence regression guard for M3 review C2 — without dedup, every
    evaluate() re-emits a fresh-UUID recommendation for already-seen incidents."""
    orch = PipelineOrchestrator()
    orch.ingest(_envelope(source="github"), received_at=_T0)
    orch.record_anomalies([_anomaly(at=_T0 + timedelta(seconds=30))])

    first = orch.evaluate(window_seconds=300.0)
    second = orch.evaluate(window_seconds=300.0)

    assert len(first) == 1
    assert second == []
    assert orch.snapshot()["recommendations"] == 1


def test_orchestrator_evaluate_picks_up_only_genuinely_new_incidents() -> None:
    orch = PipelineOrchestrator()
    orch.ingest(_envelope(source="github"), received_at=_T0)
    orch.record_anomalies([_anomaly(at=_T0 + timedelta(seconds=30))])
    first = orch.evaluate(window_seconds=300.0)
    assert len(first) == 1

    # Add a SECOND incident, far in the future so it doesn't merge.
    later = _T0 + timedelta(hours=2)
    orch.ingest(_envelope(source="github"), received_at=later)
    orch.record_anomalies([_anomaly(at=later + timedelta(seconds=30))])
    second = orch.evaluate(window_seconds=300.0)
    assert len(second) == 1
    assert second[0].recommendation_id != first[0].recommendation_id


def test_orchestrator_record_normalized_appends_event_directly() -> None:
    """``record_normalized`` is for callers that already hold a
    NormalizedEvent (e.g. the agentic-workflow usage endpoint).
    """
    orch = PipelineOrchestrator()
    event = NormalizedEvent(
        event_id=uuid4(),
        received_at=_T0,
        occurred_at=_T0,
        source="agentic-workflow",
        kind="workflow-failure",
        severity="warning",
        attributes={"workflow.name": "ci"},
    )
    orch.record_normalized(event)
    assert orch.snapshot()["events"] == 1

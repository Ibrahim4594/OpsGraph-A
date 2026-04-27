"""Recommendation engine: rules + evidence trace."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from repopulse.anomaly.detector import Anomaly
from repopulse.correlation.engine import Incident
from repopulse.pipeline.normalize import NormalizedEvent
from repopulse.recommend.engine import Recommendation, recommend

_T0 = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


def _event(*, source: str = "github", severity: str = "info") -> NormalizedEvent:
    return NormalizedEvent(
        event_id=uuid4(),
        received_at=_T0,
        occurred_at=_T0,
        source=source,
        kind="push",
        severity=severity,  # type: ignore[arg-type]
        attributes={},
    )


def _anomaly(*, source: str = "otel-metrics", severity: str = "warning") -> Anomaly:
    return Anomaly(
        timestamp=_T0,
        value=100.0,
        baseline_median=10.0,
        baseline_mad=1.0,
        score=10.0 if severity == "warning" else 20.0,
        severity=severity,  # type: ignore[arg-type]
        series_name=source,
    )


def _incident(*, anomalies: list[Anomaly], events: list[NormalizedEvent]) -> Incident:
    sources = sorted({a.series_name for a in anomalies} | {e.source for e in events})
    return Incident(
        incident_id=uuid4(),
        started_at=_T0,
        ended_at=_T0 + timedelta(seconds=60),
        sources=tuple(sources),
        anomalies=tuple(anomalies),
        events=tuple(events),
    )


# --- R1: empty incident → observe ---

def test_recommend_empty_incident_observes() -> None:
    inc = _incident(anomalies=[], events=[])
    r = recommend(inc)
    assert r.action_category == "observe"
    assert r.confidence == 0.50
    assert r.risk_level == "low"
    assert any("R1" in line for line in r.evidence_trace)


# --- R2: exactly 1 anomaly, no critical events → triage ---

def test_recommend_single_warning_anomaly_triages() -> None:
    inc = _incident(anomalies=[_anomaly(severity="warning")], events=[])
    r = recommend(inc)
    assert r.action_category == "triage"
    assert r.confidence == 0.70
    assert r.risk_level == "low"
    assert any("R2" in line for line in r.evidence_trace)


# --- R3: ≥2 anomalies OR any critical event/anomaly → escalate ---

def test_recommend_two_anomalies_escalates() -> None:
    inc = _incident(
        anomalies=[_anomaly(severity="warning"), _anomaly(severity="warning")],
        events=[],
    )
    r = recommend(inc)
    assert r.action_category == "escalate"
    assert r.confidence == 0.85
    assert r.risk_level == "medium"


def test_recommend_critical_event_alone_escalates() -> None:
    inc = _incident(anomalies=[], events=[_event(severity="critical")])
    r = recommend(inc)
    assert r.action_category == "escalate"


def test_recommend_critical_anomaly_alone_escalates() -> None:
    inc = _incident(anomalies=[_anomaly(severity="critical")], events=[])
    r = recommend(inc)
    assert r.action_category == "escalate"


def test_recommend_one_anomaly_with_critical_event_escalates_not_triages() -> None:
    """Critical event drags an otherwise-triage incident into escalate. Same-source
    so R4 (multi-source + critical → rollback) does NOT pre-empt R3."""
    inc = _incident(
        anomalies=[_anomaly(severity="warning", source="github")],
        events=[_event(severity="critical", source="github")],
    )
    r = recommend(inc)
    assert r.action_category == "escalate"


# --- R4: multi-source AND any critical → rollback ---

def test_recommend_multi_source_with_critical_rollbacks() -> None:
    inc = _incident(
        anomalies=[_anomaly(severity="critical", source="otel-metrics")],
        events=[_event(source="github")],
    )
    r = recommend(inc)
    assert r.action_category == "rollback"
    assert r.confidence == 0.90
    assert r.risk_level == "high"
    assert any("R4" in line for line in r.evidence_trace)


def test_recommend_multi_source_without_critical_does_not_rollback() -> None:
    """Multi-source alone (no critical) must not trip R4. Without a critical event
    OR ≥2 anomalies, R3 does not fire either — R2 (triage) is correct here."""
    inc = _incident(
        anomalies=[_anomaly(severity="warning", source="otel-metrics")],
        events=[_event(severity="info", source="github")],
    )
    r = recommend(inc)
    assert r.action_category != "rollback"
    assert r.action_category == "triage"


# --- evidence_trace + identity ---

def test_recommend_evidence_trace_lists_all_fired_rules_for_rollback_case() -> None:
    inc = _incident(
        anomalies=[_anomaly(severity="critical", source="otel-metrics")],
        events=[_event(source="github")],
    )
    r = recommend(inc)
    # R4 is the highest, but R3 (≥1 critical) also fires. Both should appear.
    assert any("R4" in line for line in r.evidence_trace)
    assert any("R3" in line for line in r.evidence_trace)


def test_recommend_returns_dataclass_with_unique_id_per_call() -> None:
    inc = _incident(anomalies=[], events=[])
    r1 = recommend(inc)
    r2 = recommend(inc)
    assert isinstance(r1, Recommendation)
    assert r1.recommendation_id != r2.recommendation_id
    assert r1.incident_id == inc.incident_id


def test_recommend_confidence_in_unit_interval() -> None:
    for inc in [
        _incident(anomalies=[], events=[]),
        _incident(anomalies=[_anomaly()], events=[]),
        _incident(
            anomalies=[_anomaly(severity="critical", source="otel-metrics")],
            events=[_event(source="github")],
        ),
    ]:
        r = recommend(inc)
        assert 0.0 <= r.confidence <= 1.0

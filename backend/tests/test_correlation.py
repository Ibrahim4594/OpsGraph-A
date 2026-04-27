"""Correlation engine: group anomalies + events into incidents."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from repopulse.anomaly.detector import Anomaly
from repopulse.correlation.engine import Incident, correlate
from repopulse.pipeline.normalize import NormalizedEvent

_T0 = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


def _event(*, at: datetime, source: str = "github", severity: str = "info") -> NormalizedEvent:
    return NormalizedEvent(
        event_id=uuid4(),
        received_at=at,
        occurred_at=at,
        source=source,
        kind="push",
        severity=severity,  # type: ignore[arg-type]
        attributes={},
    )


def _anomaly(*, at: datetime, source: str = "otel-metrics") -> Anomaly:
    return Anomaly(
        timestamp=at,
        value=100.0,
        baseline_median=10.0,
        baseline_mad=1.0,
        score=15.0,
        severity="critical",
        series_name=source,
    )


def test_correlate_empty_inputs_returns_empty() -> None:
    assert correlate(anomalies=[], events=[]) == []


def test_correlate_single_event_creates_one_incident() -> None:
    e = _event(at=_T0)
    incidents = correlate(anomalies=[], events=[e])
    assert len(incidents) == 1
    assert incidents[0].events == (e,)
    assert incidents[0].started_at == _T0
    assert incidents[0].ended_at == _T0
    assert incidents[0].sources == ("github",)


def test_correlate_single_anomaly_creates_one_incident() -> None:
    a = _anomaly(at=_T0)
    incidents = correlate(anomalies=[a], events=[])
    assert len(incidents) == 1
    assert incidents[0].anomalies == (a,)
    assert incidents[0].sources == ("otel-metrics",)


def test_correlate_two_events_within_window_grouped() -> None:
    e1 = _event(at=_T0)
    e2 = _event(at=_T0 + timedelta(seconds=120))  # 2 min later, default window=300
    incidents = correlate(anomalies=[], events=[e1, e2])
    assert len(incidents) == 1
    assert incidents[0].started_at == _T0
    assert incidents[0].ended_at == _T0 + timedelta(seconds=120)
    assert {ev.event_id for ev in incidents[0].events} == {e1.event_id, e2.event_id}


def test_correlate_two_events_outside_window_separate_incidents() -> None:
    e1 = _event(at=_T0)
    e2 = _event(at=_T0 + timedelta(seconds=600))  # 10 min later
    incidents = correlate(anomalies=[], events=[e1, e2], window_seconds=300.0)
    assert len(incidents) == 2


def test_correlate_mixed_input_retains_both_kinds() -> None:
    e = _event(at=_T0)
    a = _anomaly(at=_T0 + timedelta(seconds=60))
    incidents = correlate(anomalies=[a], events=[e])
    assert len(incidents) == 1
    assert incidents[0].events == (e,)
    assert incidents[0].anomalies == (a,)


def test_correlate_multi_source_incident_sources_sorted_unique() -> None:
    e_gh = _event(at=_T0, source="github")
    e_log = _event(at=_T0 + timedelta(seconds=30), source="otel-logs")
    a_metric = _anomaly(at=_T0 + timedelta(seconds=60), source="otel-metrics")
    incidents = correlate(anomalies=[a_metric], events=[e_gh, e_log])
    assert len(incidents) == 1
    assert incidents[0].sources == ("github", "otel-logs", "otel-metrics")


def test_correlate_window_boundary_inclusive() -> None:
    """An item exactly window_seconds after the previous one is part of the same incident."""
    e1 = _event(at=_T0)
    e2 = _event(at=_T0 + timedelta(seconds=300))
    incidents = correlate(anomalies=[], events=[e1, e2], window_seconds=300.0)
    assert len(incidents) == 1


def test_correlate_returns_incident_dataclass() -> None:
    incidents = correlate(anomalies=[], events=[_event(at=_T0)])
    assert isinstance(incidents[0], Incident)
    assert incidents[0].incident_id is not None


def test_correlate_handles_unsorted_input() -> None:
    e_late = _event(at=_T0 + timedelta(seconds=120))
    e_early = _event(at=_T0)
    incidents = correlate(anomalies=[], events=[e_late, e_early])
    assert len(incidents) == 1
    assert incidents[0].started_at == _T0
    assert incidents[0].ended_at == _T0 + timedelta(seconds=120)


def test_correlate_three_separate_clusters() -> None:
    e1 = _event(at=_T0)
    e2 = _event(at=_T0 + timedelta(seconds=120))                 # cluster 1 with e1
    e3 = _event(at=_T0 + timedelta(seconds=600))                 # cluster 2 alone
    e4 = _event(at=_T0 + timedelta(seconds=1200))                # cluster 3 alone
    incidents = correlate(anomalies=[], events=[e1, e2, e3, e4], window_seconds=300.0)
    assert len(incidents) == 3

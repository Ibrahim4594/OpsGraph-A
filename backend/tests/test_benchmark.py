"""Benchmark harness contract."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.scripts.benchmark import (
    BenchmarkResult,
    Scenario,
    ScenarioEvent,
    run_scenario,
    summarize,
)

_T0 = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)


def _scenario_quiet() -> Scenario:
    """Single benign event → R1 (observe)."""
    return Scenario(
        name="quiet",
        expected_action_category="observe",
        events=[
            ScenarioEvent(
                offset_seconds=0,
                envelope=EventEnvelope.model_validate(
                    {
                        "event_id": uuid4(),
                        "source": "github",
                        "kind": "push",
                        "payload": {},
                    }
                ),
            ),
        ],
        anomalies=[],
    )


def _scenario_anomaly_fast() -> Scenario:
    return Scenario(
        name="anomaly-fast",
        expected_action_category="escalate",
        events=[
            ScenarioEvent(
                offset_seconds=0,
                envelope=EventEnvelope.model_validate(
                    {
                        "event_id": uuid4(),
                        "source": "github",
                        "kind": "push",
                        "payload": {},
                    }
                ),
            ),
        ],
        anomalies=[
            Anomaly(
                timestamp=_T0 + timedelta(seconds=10),
                value=200.0,
                baseline_median=10.0,
                baseline_mad=1.0,
                score=20.0,
                severity="critical",
                series_name="otel-metrics",
            ),
        ],
    )


def test_run_scenario_quiet_emits_observe() -> None:
    result = run_scenario(_scenario_quiet(), now=_T0)
    assert isinstance(result, BenchmarkResult)
    assert result.scenario_name == "quiet"
    assert result.action_category == "observe"
    assert result.false_positive is False


def test_run_scenario_quiet_has_no_mttr_to_record() -> None:
    """No anomalies → no anomaly→rec interval to time → MTTR is None."""
    result = run_scenario(_scenario_quiet(), now=_T0)
    assert result.mttr_seconds is None


def test_run_scenario_anomaly_records_mttr() -> None:
    result = run_scenario(_scenario_anomaly_fast(), now=_T0)
    assert result.action_category in {"escalate", "rollback"}
    assert result.mttr_seconds is not None
    assert result.mttr_seconds >= 0.0


def test_run_scenario_marks_false_positive_when_category_differs() -> None:
    # Quiet scenario but expectation set to "rollback" — should be FP.
    quiet = _scenario_quiet()
    misexpected = Scenario(
        name=quiet.name,
        expected_action_category="rollback",
        events=quiet.events,
        anomalies=quiet.anomalies,
    )
    result = run_scenario(misexpected, now=_T0)
    assert result.false_positive is True


def test_summarize_aggregates_false_positive_rate() -> None:
    results = [
        BenchmarkResult(
            scenario_name="a",
            action_category="observe",
            expected_action_category="observe",
            false_positive=False,
            mttr_seconds=None,
            burn_rate_lead_seconds=None,
        ),
        BenchmarkResult(
            scenario_name="b",
            action_category="triage",
            expected_action_category="escalate",
            false_positive=True,
            mttr_seconds=5.0,
            burn_rate_lead_seconds=2.0,
        ),
    ]
    summary = summarize(results)
    assert summary["scenarios"] == 2
    assert summary["false_positive_rate"] == 0.5
    assert summary["false_positives"] == 1
    assert summary["mttr_seconds_avg"] == 5.0


def test_summarize_handles_empty_input() -> None:
    summary = summarize([])
    assert summary["scenarios"] == 0
    assert summary["false_positive_rate"] == 0.0
    assert summary["mttr_seconds_avg"] is None

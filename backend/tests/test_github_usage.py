"""Tests for the workflow usage telemetry mapping."""
from __future__ import annotations

from datetime import UTC, datetime

from repopulse.github.usage import WorkflowUsage, record_run, to_normalized_event


def test_workflow_usage_holds_fields() -> None:
    usage = WorkflowUsage(
        workflow_name="agentic-issue-triage",
        run_id=123,
        duration_seconds=42.0,
        conclusion="success",
        repository="x/y",
        cost_estimate_usd=42.0 / 60.0 * 0.008,
    )
    assert usage.workflow_name == "agentic-issue-triage"
    assert round(usage.cost_estimate_usd, 6) == round(42 / 60 * 0.008, 6)


def test_record_run_computes_cost_for_linux() -> None:
    usage = record_run(
        workflow_name="ci",
        run_id=999,
        duration_seconds=120.0,
        conclusion="success",
        repository="x/y",
        runner="linux",
    )
    assert usage.cost_estimate_usd == 120.0 / 60.0 * 0.008


def test_record_run_zero_cost_for_unknown_runner() -> None:
    usage = record_run(
        workflow_name="ci",
        run_id=1,
        duration_seconds=10.0,
        conclusion="success",
        repository="x/y",
        runner="self-hosted",
    )
    assert usage.cost_estimate_usd == 0.0


def test_record_run_costs_macos_higher_than_linux() -> None:
    linux = record_run(
        workflow_name="ci", run_id=1, duration_seconds=60.0,
        conclusion="success", repository="x/y", runner="linux",
    )
    macos = record_run(
        workflow_name="ci", run_id=2, duration_seconds=60.0,
        conclusion="success", repository="x/y", runner="macos",
    )
    assert macos.cost_estimate_usd > linux.cost_estimate_usd


def test_to_normalized_event_failure_shape() -> None:
    usage = record_run(
        workflow_name="agentic-doc-drift",
        run_id=7,
        duration_seconds=30.0,
        conclusion="failure",
        repository="x/y",
        runner="linux",
    )
    received_at = datetime(2026, 4, 27, 12, tzinfo=UTC)
    event = to_normalized_event(usage, received_at=received_at)
    assert event.source == "agentic-workflow"
    assert event.kind == "workflow-failure"
    assert event.severity == "warning"
    assert event.received_at == received_at
    assert event.occurred_at == received_at
    assert event.attributes["workflow.name"] == "agentic-doc-drift"
    assert event.attributes["workflow.run_id"] == "7"
    assert event.attributes["workflow.conclusion"] == "failure"


def test_to_normalized_event_success_shape() -> None:
    usage = record_run(
        workflow_name="ci",
        run_id=1,
        duration_seconds=10.0,
        conclusion="success",
        repository="x/y",
        runner="linux",
    )
    received_at = datetime(2026, 4, 27, 13, tzinfo=UTC)
    event = to_normalized_event(usage, received_at=received_at)
    assert event.kind == "workflow-success"
    assert event.severity == "info"


def test_to_normalized_event_other_conclusion() -> None:
    usage = record_run(
        workflow_name="ci",
        run_id=1,
        duration_seconds=5.0,
        conclusion="cancelled",
        repository="x/y",
        runner="linux",
    )
    event = to_normalized_event(usage, received_at=datetime.now(UTC))
    assert event.kind == "workflow-other"
    assert event.severity == "info"

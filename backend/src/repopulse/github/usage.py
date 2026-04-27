"""Workflow run usage telemetry.

Static cost rates (USD/min) per GitHub-hosted runner type. Real billing
arrives from GitHub's billing API in a later milestone; the fixed rates are
documented as a stand-in in ADR-003.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from repopulse.pipeline.normalize import NormalizedEvent, Severity

_RUNNER_RATES_USD_PER_MIN: dict[str, float] = {
    "linux": 0.008,
    "windows": 0.016,
    "macos": 0.08,
}


@dataclass(frozen=True)
class WorkflowUsage:
    workflow_name: str
    run_id: int
    duration_seconds: float
    conclusion: str
    repository: str
    cost_estimate_usd: float


def record_run(
    *,
    workflow_name: str,
    run_id: int,
    duration_seconds: float,
    conclusion: str,
    repository: str,
    runner: str,
) -> WorkflowUsage:
    rate = _RUNNER_RATES_USD_PER_MIN.get(runner, 0.0)
    cost = duration_seconds / 60.0 * rate
    return WorkflowUsage(
        workflow_name=workflow_name,
        run_id=run_id,
        duration_seconds=duration_seconds,
        conclusion=conclusion,
        repository=repository,
        cost_estimate_usd=cost,
    )


def to_normalized_event(
    usage: WorkflowUsage, *, received_at: datetime
) -> NormalizedEvent:
    kind: str
    severity: Severity
    if usage.conclusion == "success":
        kind = "workflow-success"
        severity = "info"
    elif usage.conclusion == "failure":
        kind = "workflow-failure"
        severity = "warning"
    else:
        kind = "workflow-other"
        severity = "info"
    return NormalizedEvent(
        event_id=uuid4(),
        received_at=received_at,
        occurred_at=received_at,
        source="agentic-workflow",
        kind=kind,
        severity=severity,
        attributes={
            "workflow.name": usage.workflow_name,
            "workflow.run_id": str(usage.run_id),
            "workflow.conclusion": usage.conclusion,
            "workflow.duration_seconds": f"{usage.duration_seconds:.3f}",
            "workflow.cost_estimate_usd": f"{usage.cost_estimate_usd:.6f}",
            "workflow.repository": usage.repository,
        },
    )

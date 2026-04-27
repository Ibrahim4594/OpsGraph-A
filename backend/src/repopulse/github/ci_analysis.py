"""CI failure analyzer.

Given a ``WorkflowRunPayload`` with ``conclusion=failure`` and the list of
failed-job log excerpts, classify the likely cause and propose a next action.
Pure function; no I/O.

Cause-precedence policy when multiple jobs fail with different causes:

- The **first job to match a known pattern wins** the top-level
  ``likely_cause``. All other jobs' matches are still recorded in
  ``evidence_trace`` for transparency.
- Rationale: the first failed job is usually the root cause; downstream
  jobs that fail because the first job failed (e.g., a deploy job after a
  test job) would otherwise drown out the real signal. Operators can read
  the trace to see the full picture if the heuristic is wrong.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from repopulse.github.payloads import WorkflowRunPayload

Cause = Literal["timeout", "dependency", "test-failure", "syntax", "unknown"]
NextAction = Literal[
    "rerun", "fix-deps", "investigate-test", "fix-syntax", "manual-review"
]

_PATTERNS: tuple[tuple[Cause, re.Pattern[str]], ...] = (
    ("timeout", re.compile(r"\b(timeout|timed out|deadline)\b", re.IGNORECASE)),
    (
        "dependency",
        re.compile(r"(ModuleNotFoundError|ImportError|cannot find module)"),
    ),
    ("syntax", re.compile(r"(SyntaxError|ParseError|unexpected token)")),
    (
        "test-failure",
        re.compile(r"\b(AssertionError|FAILED|test .* failed)\b"),
    ),
)

_NEXT: dict[Cause, NextAction] = {
    "timeout": "rerun",
    "dependency": "fix-deps",
    "test-failure": "investigate-test",
    "syntax": "fix-syntax",
    "unknown": "manual-review",
}


@dataclass(frozen=True)
class CIFailureSummary:
    workflow_run_id: int
    head_sha: str
    head_branch: str
    failed_jobs: tuple[tuple[str, str], ...]
    likely_cause: Cause
    next_action: NextAction
    evidence_trace: tuple[str, ...]


def summarize_failure(
    payload: WorkflowRunPayload,
    *,
    failed_jobs: list[tuple[str, str, str]],
) -> CIFailureSummary:
    if payload.workflow_run.conclusion != "failure":
        raise ValueError(
            "summarize_failure requires conclusion='failure', got "
            f"{payload.workflow_run.conclusion!r}"
        )

    cause: Cause = "unknown"
    trace: list[str] = []

    for job_name, _step, excerpt in failed_jobs:
        matched = False
        for candidate, pattern in _PATTERNS:
            if pattern.search(excerpt):
                if cause == "unknown":
                    cause = candidate
                trace.append(
                    f"{candidate}: {pattern.pattern} matched in job {job_name!r}"
                )
                matched = True
                break
        if not matched:
            trace.append(f"unknown: no pattern matched in job {job_name!r}")

    if not trace:
        trace.append("unknown: no failed-job excerpts provided")

    return CIFailureSummary(
        workflow_run_id=payload.workflow_run.id,
        head_sha=payload.workflow_run.head_sha,
        head_branch=payload.workflow_run.head_branch,
        failed_jobs=tuple((j, s) for j, s, _ in failed_jobs),
        likely_cause=cause,
        next_action=_NEXT[cause],
        evidence_trace=tuple(trace),
    )

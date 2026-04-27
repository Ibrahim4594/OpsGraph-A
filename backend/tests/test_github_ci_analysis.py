"""Tests for the GitHub CI failure analyzer."""
from __future__ import annotations

import pytest

from repopulse.github.ci_analysis import CIFailureSummary, summarize_failure
from repopulse.github.payloads import WorkflowRunPayload


def _run(conclusion: str = "failure") -> WorkflowRunPayload:
    return WorkflowRunPayload.model_validate(
        {
            "action": "completed",
            "workflow_run": {
                "id": 100,
                "name": "ci",
                "conclusion": conclusion,
                "head_branch": "fix/x",
                "head_sha": "abc",
                "html_url": "https://github.com/x/y/actions/runs/100",
                "run_attempt": 1,
            },
            "repository": {"full_name": "x/y"},
        }
    )


def test_summarize_timeout_returns_rerun() -> None:
    summary = summarize_failure(
        _run(),
        failed_jobs=[("backend", "Test (pytest)", "E   Timed out after 600s")],
    )
    assert isinstance(summary, CIFailureSummary)
    assert summary.likely_cause == "timeout"
    assert summary.next_action == "rerun"
    assert summary.failed_jobs == (("backend", "Test (pytest)"),)


def test_summarize_module_error_returns_fix_deps() -> None:
    summary = summarize_failure(
        _run(),
        failed_jobs=[
            ("backend", "Install", "ModuleNotFoundError: No module named 'foo'")
        ],
    )
    assert summary.likely_cause == "dependency"
    assert summary.next_action == "fix-deps"


def test_summarize_test_failure_returns_investigate() -> None:
    summary = summarize_failure(
        _run(),
        failed_jobs=[
            ("backend", "Test", "FAILED tests/test_x.py::test_y - AssertionError")
        ],
    )
    assert summary.likely_cause == "test-failure"
    assert summary.next_action == "investigate-test"


def test_summarize_syntax_error_returns_fix_syntax() -> None:
    summary = summarize_failure(
        _run(),
        failed_jobs=[("backend", "Lint", "SyntaxError: unexpected token")],
    )
    assert summary.likely_cause == "syntax"
    assert summary.next_action == "fix-syntax"


def test_summarize_unknown_returns_manual_review() -> None:
    summary = summarize_failure(
        _run(),
        failed_jobs=[("backend", "Step", "some opaque error")],
    )
    assert summary.likely_cause == "unknown"
    assert summary.next_action == "manual-review"


def test_summarize_rejects_non_failure() -> None:
    with pytest.raises(ValueError, match="conclusion='failure'"):
        summarize_failure(_run(conclusion="success"), failed_jobs=[])


def test_summarize_carries_run_metadata() -> None:
    summary = summarize_failure(
        _run(),
        failed_jobs=[("backend", "Test", "AssertionError")],
    )
    assert summary.workflow_run_id == 100
    assert summary.head_sha == "abc"
    assert summary.head_branch == "fix/x"


def test_summarize_first_match_wins_when_multiple_jobs() -> None:
    summary = summarize_failure(
        _run(),
        failed_jobs=[
            ("a", "Test", "AssertionError: nope"),
            ("b", "Install", "ModuleNotFoundError"),
        ],
    )
    # First-pattern-precedence within job: timeout > dependency > syntax > test-failure
    # But across jobs we keep the *first* assigned cause (test-failure here).
    assert summary.likely_cause == "test-failure"
    # All jobs present in failed_jobs.
    assert {j[0] for j in summary.failed_jobs} == {"a", "b"}


def test_summarize_records_evidence_per_job() -> None:
    summary = summarize_failure(
        _run(),
        failed_jobs=[
            ("a", "Test", "AssertionError: nope"),
            ("b", "Install", "ModuleNotFoundError"),
        ],
    )
    assert any("test-failure" in line and "'a'" in line for line in summary.evidence_trace)
    assert any("dependency" in line and "'b'" in line for line in summary.evidence_trace)

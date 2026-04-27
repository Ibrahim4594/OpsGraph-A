"""Tests for GitHub event payload models."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from repopulse.github.payloads import (
    IssuePayload,
    PullRequestPayload,
    WorkflowRunPayload,
)


def test_issue_payload_minimal_parses() -> None:
    payload = IssuePayload.model_validate(
        {
            "action": "opened",
            "issue": {
                "number": 42,
                "title": "App crashes on startup",
                "body": "Stack trace: NullPointer...",
                "labels": [{"name": "bug"}],
                "user": {"login": "alice"},
            },
            "repository": {"full_name": "Ibrahim4594/OpsGraph-A"},
        }
    )
    assert payload.issue.number == 42
    assert payload.issue.title == "App crashes on startup"
    assert payload.issue.label_names == ("bug",)
    assert payload.repository.full_name == "Ibrahim4594/OpsGraph-A"


def test_issue_payload_rejects_unknown_action() -> None:
    with pytest.raises(ValidationError):
        IssuePayload.model_validate(
            {
                "action": "exploded",
                "issue": {
                    "number": 1,
                    "title": "x",
                    "body": "",
                    "labels": [],
                    "user": {"login": "a"},
                },
                "repository": {"full_name": "x/y"},
            }
        )


def test_issue_payload_handles_missing_body() -> None:
    payload = IssuePayload.model_validate(
        {
            "action": "opened",
            "issue": {
                "number": 1,
                "title": "x",
                "labels": [],
                "user": {"login": "a"},
            },
            "repository": {"full_name": "x/y"},
        }
    )
    assert payload.issue.body is None


def test_workflow_run_payload_failure_parses() -> None:
    payload = WorkflowRunPayload.model_validate(
        {
            "action": "completed",
            "workflow_run": {
                "id": 999,
                "name": "ci",
                "conclusion": "failure",
                "head_branch": "fix/auth",
                "head_sha": "deadbeef",
                "html_url": "https://github.com/x/y/actions/runs/999",
                "run_attempt": 1,
            },
            "repository": {"full_name": "x/y"},
        }
    )
    assert payload.workflow_run.conclusion == "failure"
    assert payload.workflow_run.head_sha == "deadbeef"
    assert payload.workflow_run.run_attempt == 1


def test_workflow_run_payload_rejects_bad_conclusion() -> None:
    with pytest.raises(ValidationError):
        WorkflowRunPayload.model_validate(
            {
                "action": "completed",
                "workflow_run": {
                    "id": 1,
                    "name": "ci",
                    "conclusion": "exploded",
                    "head_branch": "x",
                    "head_sha": "a",
                    "html_url": "https://x",
                    "run_attempt": 1,
                },
                "repository": {"full_name": "x/y"},
            }
        )


def test_pull_request_payload_parses() -> None:
    payload = PullRequestPayload.model_validate(
        {
            "action": "opened",
            "pull_request": {
                "number": 7,
                "title": "Update docs",
                "head": {"sha": "cafe"},
                "base": {"ref": "main"},
            },
            "repository": {"full_name": "x/y"},
        }
    )
    assert payload.pull_request.number == 7
    assert payload.pull_request.head.sha == "cafe"
    assert payload.pull_request.base.ref == "main"

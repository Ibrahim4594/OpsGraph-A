"""Pydantic models for the subset of GitHub event payloads we read.

Intentionally narrow: only the fields the agentic workflows post to the backend.
Full webhook schemas live in GitHub's docs; we don't shadow them.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class _Repository(BaseModel):
    full_name: str


class _IssueUser(BaseModel):
    login: str


class _IssueLabel(BaseModel):
    name: str


class _Issue(BaseModel):
    number: int
    title: str
    body: str | None = None
    labels: list[_IssueLabel] = Field(default_factory=list)
    user: _IssueUser

    @property
    def label_names(self) -> tuple[str, ...]:
        return tuple(label.name for label in self.labels)


class IssuePayload(BaseModel):
    action: Literal["opened", "reopened", "edited"]
    issue: _Issue
    repository: _Repository


class _WorkflowRun(BaseModel):
    id: int
    name: str
    conclusion: Literal[
        "success", "failure", "cancelled", "skipped", "neutral", "timed_out"
    ]
    head_branch: str
    head_sha: str
    html_url: str
    run_attempt: int


class WorkflowRunPayload(BaseModel):
    action: Literal["completed", "requested", "in_progress"]
    workflow_run: _WorkflowRun
    repository: _Repository


class _PRRef(BaseModel):
    sha: str | None = None
    ref: str | None = None


class _PullRequest(BaseModel):
    number: int
    title: str
    head: _PRRef
    base: _PRRef


class PullRequestPayload(BaseModel):
    action: Literal["opened", "synchronize", "reopened", "edited"]
    pull_request: _PullRequest
    repository: _Repository

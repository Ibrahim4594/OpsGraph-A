"""GitHub agentic-workflow HTTP endpoints.

POST /api/v1/github/triage       — classify a GitHub issue
POST /api/v1/github/ci-failure   — summarize a failed workflow_run
POST /api/v1/github/doc-drift    — find broken markdown refs in a PR diff
POST /api/v1/github/usage        — ingest a workflow-run usage record

All four endpoints require ``Authorization: Bearer <REPOPULSE_AGENTIC_SHARED_SECRET>``
and short-circuit to ``202 {"disabled": true}`` when ``REPOPULSE_AGENTIC_ENABLED``
is ``false``. See ADR-003 for the trust model.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from repopulse.config import Settings
from repopulse.github.ci_analysis import summarize_failure
from repopulse.github.doc_drift import find_broken_refs
from repopulse.github.payloads import IssuePayload, WorkflowRunPayload
from repopulse.github.triage import classify_issue
from repopulse.github.usage import record_run, to_normalized_event

router = APIRouter(prefix="/api/v1/github", tags=["github"])


def _get_settings() -> Settings:
    """Build a fresh ``Settings`` per request.

    pydantic-settings reads env vars at construction time, so this honors
    the ``REPOPULSE_AGENTIC_ENABLED`` / ``REPOPULSE_AGENTIC_SHARED_SECRET``
    kill-switch claim that flipping the env var takes effect immediately
    without a process restart (see ADR-003 §3 and docs/agentic-workflows.md).
    """
    return Settings()


def _auth(
    settings: Annotated[Settings, Depends(_get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> Settings:
    expected = settings.agentic_shared_secret
    if not expected:
        raise HTTPException(
            status_code=503, detail="agentic shared secret not configured"
        )
    token = (authorization or "").removeprefix("Bearer ").strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="invalid agentic token")
    return settings


def _disabled_response() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "disabled": True,
            "reason": "REPOPULSE_AGENTIC_ENABLED=false",
        },
    )


# Per-field length limits keep request bodies bounded so a noisy or
# malicious workflow run cannot OOM the backend. Numbers chosen to be
# generous for legitimate use (e.g. ~500 changed files in a big PR) but
# block obviously oversized payloads.
_MAX_LOG_EXCERPT = 8 * 1024  # 8 KiB per failed-job excerpt
_MAX_FAILED_JOBS = 50
_MAX_CHANGED_FILES = 500
_MAX_REPO_PATHS = 50_000
_MAX_FILE_CONTENT_BYTES = 256 * 1024  # 256 KiB per file
_MAX_FILE_PATH = 1024


class _FailedJob(BaseModel):
    job_name: str = Field(max_length=_MAX_FILE_PATH)
    step: str = Field(max_length=_MAX_FILE_PATH)
    log_excerpt: str = Field(max_length=_MAX_LOG_EXCERPT)


class _CIFailureBody(BaseModel):
    payload: WorkflowRunPayload
    failed_jobs: list[_FailedJob] = Field(max_length=_MAX_FAILED_JOBS)


class _DocDriftBody(BaseModel):
    changed_files: list[str] = Field(max_length=_MAX_CHANGED_FILES)
    repo_paths: list[str] = Field(max_length=_MAX_REPO_PATHS)
    file_contents: dict[str, str] = Field(default_factory=dict)


class _UsageBody(BaseModel):
    workflow_name: str = Field(max_length=_MAX_FILE_PATH)
    run_id: int
    duration_seconds: float = Field(ge=0.0)
    conclusion: str = Field(max_length=64)
    repository: str = Field(max_length=_MAX_FILE_PATH)
    runner: str = Field(max_length=64)


@router.post("/triage", response_model=None)
def triage(
    payload: IssuePayload,
    settings: Annotated[Settings, Depends(_auth)],
) -> JSONResponse | dict[str, object]:
    if not settings.agentic_enabled:
        return _disabled_response()
    rec = classify_issue(payload)
    return {
        "issue_number": rec.issue_number,
        "severity": rec.severity,
        "category": rec.category,
        "suggested_labels": list(rec.suggested_labels),
        "confidence": rec.confidence,
        "evidence_trace": list(rec.evidence_trace),
    }


@router.post("/ci-failure", response_model=None)
def ci_failure(
    body: _CIFailureBody,
    settings: Annotated[Settings, Depends(_auth)],
) -> JSONResponse | dict[str, object]:
    if not settings.agentic_enabled:
        return _disabled_response()
    summary = summarize_failure(
        body.payload,
        failed_jobs=[
            (job.job_name, job.step, job.log_excerpt) for job in body.failed_jobs
        ],
    )
    return {
        "workflow_run_id": summary.workflow_run_id,
        "head_sha": summary.head_sha,
        "head_branch": summary.head_branch,
        "failed_jobs": [list(j) for j in summary.failed_jobs],
        "likely_cause": summary.likely_cause,
        "next_action": summary.next_action,
        "evidence_trace": list(summary.evidence_trace),
    }


@router.post("/doc-drift", response_model=None)
def doc_drift(
    body: _DocDriftBody,
    settings: Annotated[Settings, Depends(_auth)],
) -> JSONResponse | dict[str, object]:
    if not settings.agentic_enabled:
        return _disabled_response()
    for path, content in body.file_contents.items():
        if len(content) > _MAX_FILE_CONTENT_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"file_contents[{path!r}] exceeds "
                    f"{_MAX_FILE_CONTENT_BYTES} byte cap"
                ),
            )
    report = find_broken_refs(
        changed_files=body.changed_files,
        repo_paths=set(body.repo_paths),
        file_contents=body.file_contents,
    )
    return {"broken_refs": [list(t) for t in report.broken_refs]}


@router.post("/usage", status_code=status.HTTP_202_ACCEPTED, response_model=None)
def usage(
    body: _UsageBody,
    request: Request,
    settings: Annotated[Settings, Depends(_auth)],
) -> JSONResponse | dict[str, object]:
    if not settings.agentic_enabled:
        return _disabled_response()
    record = record_run(
        workflow_name=body.workflow_name,
        run_id=body.run_id,
        duration_seconds=body.duration_seconds,
        conclusion=body.conclusion,
        repository=body.repository,
        runner=body.runner,
    )
    event = to_normalized_event(record, received_at=datetime.now(UTC))
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is not None:
        orchestrator.record_normalized(event)
        orchestrator.record_workflow_run(
            workflow_name=record.workflow_name,
            run_id=record.run_id,
            conclusion=record.conclusion,
            at=event.received_at,
        )
        orchestrator.evaluate()
    return {"accepted": True, "event_id": str(event.event_id)}

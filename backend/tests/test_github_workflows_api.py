"""Tests for the GitHub agentic-workflow HTTP endpoints.

Covers:
- Authorization (shared-secret bearer token).
- Kill switch (REPOPULSE_AGENTIC_ENABLED=false short-circuits to 202 disabled).
- Each endpoint's happy path.
- /usage ingests an event into the orchestrator.
"""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from repopulse.main import create_app


@pytest.fixture
def secret() -> str:
    return "test-secret-do-not-use"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, secret: str) -> Iterator[TestClient]:
    from repopulse.testing import make_inmem_orchestrator

    monkeypatch.setenv("REPOPULSE_AGENTIC_ENABLED", "true")
    monkeypatch.setenv("REPOPULSE_AGENTIC_SHARED_SECRET", secret)
    orch, _ = make_inmem_orchestrator()
    app = create_app(orchestrator=orch)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def auth(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


def _issue_body() -> dict[str, object]:
    return {
        "action": "opened",
        "issue": {
            "number": 5,
            "title": "Production outage",
            "body": "checkout broken",
            "labels": [],
            "user": {"login": "u"},
        },
        "repository": {"full_name": "x/y"},
    }


def test_triage_requires_auth(client: TestClient) -> None:
    response = client.post("/api/v1/github/triage", json=_issue_body())
    assert response.status_code == 401


def test_triage_returns_recommendation(
    client: TestClient, auth: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/github/triage", json=_issue_body(), headers=auth
    )
    assert response.status_code == 200
    data = response.json()
    assert data["severity"] == "critical"
    assert data["issue_number"] == 5
    assert "severity:critical" in data["suggested_labels"]


def test_kill_switch_disables_endpoint(
    monkeypatch: pytest.MonkeyPatch, secret: str
) -> None:
    monkeypatch.setenv("REPOPULSE_AGENTIC_ENABLED", "false")
    monkeypatch.setenv("REPOPULSE_AGENTIC_SHARED_SECRET", secret)
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as kc:
        response = kc.post(
            "/api/v1/github/triage",
            json=_issue_body(),
            headers={"Authorization": f"Bearer {secret}"},
        )
    assert response.status_code == 202
    assert response.json()["disabled"] is True


def test_ci_failure_endpoint(
    client: TestClient, auth: dict[str, str]
) -> None:
    body = {
        "payload": {
            "action": "completed",
            "workflow_run": {
                "id": 1,
                "name": "ci",
                "conclusion": "failure",
                "head_branch": "x",
                "head_sha": "abc",
                "html_url": "https://x",
                "run_attempt": 1,
            },
            "repository": {"full_name": "x/y"},
        },
        "failed_jobs": [
            {
                "job_name": "backend",
                "step": "Test",
                "log_excerpt": "AssertionError: nope",
            }
        ],
    }
    response = client.post(
        "/api/v1/github/ci-failure", json=body, headers=auth
    )
    assert response.status_code == 200
    assert response.json()["likely_cause"] == "test-failure"


def test_doc_drift_endpoint(
    client: TestClient, auth: dict[str, str]
) -> None:
    body = {
        "changed_files": ["docs/a.md"],
        "repo_paths": ["docs/a.md"],
        "file_contents": {"docs/a.md": "[x](missing.md)"},
    }
    response = client.post(
        "/api/v1/github/doc-drift", json=body, headers=auth
    )
    assert response.status_code == 200
    assert response.json()["broken_refs"] == [["docs/a.md", "missing.md", 1]]


async def test_usage_endpoint_ingests_event(
    client: TestClient, auth: dict[str, str]
) -> None:
    body = {
        "workflow_name": "ci",
        "run_id": 5,
        "duration_seconds": 30.0,
        "conclusion": "failure",
        "repository": "x/y",
        "runner": "linux",
    }
    response = client.post("/api/v1/github/usage", json=body, headers=auth)
    assert response.status_code == 202
    assert response.json()["accepted"] is True

    # Orchestrator should have stored the workflow event.
    from fastapi import FastAPI
    assert isinstance(client.app, FastAPI)
    orchestrator = client.app.state.orchestrator
    snapshot = await orchestrator.snapshot()
    assert snapshot["events"] >= 1


def test_missing_secret_yields_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without REPOPULSE_AGENTIC_SHARED_SECRET configured, the endpoint
    refuses to authenticate any request — 503 (mis-configured) is the
    safest signal: never accept a token when no expected token is set."""
    monkeypatch.setenv("REPOPULSE_AGENTIC_ENABLED", "true")
    monkeypatch.delenv("REPOPULSE_AGENTIC_SHARED_SECRET", raising=False)
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as nc:
        response = nc.post(
            "/api/v1/github/triage",
            json=_issue_body(),
            headers={"Authorization": "Bearer anything"},
        )
    assert response.status_code == 503


def test_wrong_secret_yields_401(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/github/triage",
        json=_issue_body(),
        headers={"Authorization": "Bearer wrong"},
    )
    assert response.status_code == 401


# Post-review fixes:


def test_kill_switch_flip_takes_effect_without_restart(
    monkeypatch: pytest.MonkeyPatch, secret: str
) -> None:
    """Regression: settings are re-read per request, so flipping
    REPOPULSE_AGENTIC_ENABLED on a running process honors the new value
    on the very next request (matches the docs' 'milliseconds' claim).
    """
    monkeypatch.setenv("REPOPULSE_AGENTIC_ENABLED", "true")
    monkeypatch.setenv("REPOPULSE_AGENTIC_SHARED_SECRET", secret)
    app = create_app()
    headers = {"Authorization": f"Bearer {secret}"}
    with TestClient(app, raise_server_exceptions=False) as tc:
        first = tc.post(
            "/api/v1/github/triage", json=_issue_body(), headers=headers
        )
        assert first.status_code == 200

        # Flip the flag on the SAME running app — must take effect now.
        monkeypatch.setenv("REPOPULSE_AGENTIC_ENABLED", "false")

        second = tc.post(
            "/api/v1/github/triage", json=_issue_body(), headers=headers
        )
    assert second.status_code == 202
    assert second.json()["disabled"] is True


def test_doc_drift_rejects_oversized_file_content(
    client: TestClient, auth: dict[str, str]
) -> None:
    """Regression: per-file content size cap (256 KiB) returns 413."""
    body = {
        "changed_files": ["docs/big.md"],
        "repo_paths": ["docs/big.md"],
        "file_contents": {"docs/big.md": "x" * (256 * 1024 + 1)},
    }
    response = client.post(
        "/api/v1/github/doc-drift", json=body, headers=auth
    )
    assert response.status_code == 413


def test_ci_failure_rejects_too_many_jobs(
    client: TestClient, auth: dict[str, str]
) -> None:
    """Regression: failed_jobs list length cap (50) returns 422."""
    body = {
        "payload": {
            "action": "completed",
            "workflow_run": {
                "id": 1, "name": "ci", "conclusion": "failure",
                "head_branch": "x", "head_sha": "abc",
                "html_url": "https://x", "run_attempt": 1,
            },
            "repository": {"full_name": "x/y"},
        },
        "failed_jobs": [
            {"job_name": f"j{i}", "step": "s", "log_excerpt": "AssertionError"}
            for i in range(51)
        ],
    }
    response = client.post(
        "/api/v1/github/ci-failure", json=body, headers=auth
    )
    assert response.status_code == 422

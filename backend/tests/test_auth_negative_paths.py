"""Negative-path auth coverage for v1.1 protected routes (post-review I3).

Pre-v1.1 only ``test_events.py`` and ``test_github_workflows_api.py``
asserted 401-on-missing-bearer / 503-on-missing-secret. The GET routes
(`recommendations`, `incidents`, `actions`, `slo`) and the approve/reject
POSTs were tested only on the happy path. The brief asks for explicit
falsifying coverage, so this module asserts that:

  - Missing/wrong bearer → 401 on every protected route.
  - Missing ``REPOPULSE_API_SHARED_SECRET`` → 503 on every protected route.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from repopulse.main import create_app

_PROTECTED_GETS = (
    "/api/v1/recommendations",
    "/api/v1/incidents",
    "/api/v1/actions",
    "/api/v1/slo",
)


@pytest.mark.parametrize("path", _PROTECTED_GETS)
def test_get_without_bearer_returns_401(path: str) -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 401


@pytest.mark.parametrize("path", _PROTECTED_GETS)
def test_get_with_wrong_bearer_returns_401(path: str) -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            path, headers={"Authorization": "Bearer wrong-secret"}
        )
    assert response.status_code == 401


@pytest.mark.parametrize("path", _PROTECTED_GETS)
def test_get_with_unset_secret_returns_503(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REPOPULSE_API_SHARED_SECRET", raising=False)
    app = create_app()
    with TestClient(app) as client:
        # Even with a Bearer present, fail-closed must win.
        response = client.get(
            path, headers={"Authorization": "Bearer anything"}
        )
    assert response.status_code == 503


def test_approve_without_bearer_returns_401() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/recommendations/00000000-0000-0000-0000-000000000000/approve"
        )
    assert response.status_code == 401


def test_reject_without_bearer_returns_401() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/recommendations/00000000-0000-0000-0000-000000000000/reject",
            json={"reason": "x"},
        )
    assert response.status_code == 401


def test_approve_with_unset_secret_returns_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REPOPULSE_API_SHARED_SECRET", raising=False)
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/recommendations/00000000-0000-0000-0000-000000000000/approve",
            headers={"Authorization": "Bearer anything"},
        )
    assert response.status_code == 503

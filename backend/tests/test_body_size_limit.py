"""Body-size limit middleware (v1.1 post-review I1).

The 256 KiB ``payload`` cap on ``POST /api/v1/events`` is a Pydantic
validator that runs *after* Starlette has parsed the body into RAM.
A malicious caller could send a 10 MB body, OOMing the worker before
the validator rejects it. The middleware enforces an upstream cap on
``Content-Length`` so the parse never starts.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from repopulse.main import create_app

_AUTH = {"Authorization": "Bearer test-pipeline-api-secret"}


def test_oversized_content_length_rejected_before_parse() -> None:
    from tests._inmem_orchestrator import make_inmem_orchestrator

    orch, _ = make_inmem_orchestrator()
    app = create_app(orchestrator=orch)
    with TestClient(app) as client:
        # 4 MiB of zeros — well above the 384 KiB request cap, well below
        # what would OOM jsdom but still proves the middleware fires.
        big = b"0" * (4 * 1024 * 1024)
        response = client.post(
            "/api/v1/events",
            content=big,
            headers={
                **_AUTH,
                "Content-Type": "application/json",
                "Content-Length": str(len(big)),
            },
        )
    assert response.status_code == 413
    assert "too large" in response.json()["detail"].lower()


def test_under_cap_passes_through() -> None:
    """Sanity: a normal-sized request still works."""
    import json
    import uuid

    from tests._inmem_orchestrator import make_inmem_orchestrator

    orch, _ = make_inmem_orchestrator()
    app = create_app(orchestrator=orch)
    body = json.dumps(
        {
            "event_id": str(uuid.uuid4()),
            "source": "github",
            "kind": "push",
            "payload": {"sha": "abc"},
        }
    ).encode()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/events",
            content=body,
            headers={
                **_AUTH,
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
    assert response.status_code == 202

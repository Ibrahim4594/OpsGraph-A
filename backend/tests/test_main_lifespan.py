"""FastAPI lifespan + DB-mode wiring tests (M2.0 task 6).

Production path:

- ``REPOPULSE_DATABASE_URL`` set + no orchestrator injected → ``create_app``
  builds an :class:`AsyncEngine` (lazily — no socket opens), wraps it in
  an ``async_sessionmaker``, and constructs the async
  :class:`PipelineOrchestrator` over that sessionmaker. The engine is
  exposed on ``app.state.engine`` and disposed on shutdown.
- ``REPOPULSE_DATABASE_URL`` unset + no orchestrator injected →
  ``create_app`` raises :class:`RuntimeError` immediately. v2.0 has no
  in-memory production path; misconfiguration must be loud.

Test path:

- ``orchestrator=`` injected (built via
  :func:`tests._inmem_orchestrator.make_inmem_orchestrator`) bypasses
  the engine entirely. ``app.state.engine`` is ``None``.

The lifespan startup itself is a no-op for the orchestrator (the engine
is constructed eagerly inside ``create_app`` so OTel can patch the
middleware stack before any request lands — see the module docstring
of ``repopulse.main``); shutdown is what the lifespan owns. We assert
``engine.dispose`` runs by spying on the ``AsyncEngine``.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from repopulse.main import create_app
from tests._inmem_orchestrator import make_inmem_orchestrator


def test_create_app_with_inmem_orchestrator_does_not_build_engine() -> None:
    """Test path: injecting an orchestrator skips engine construction.

    ``app.state.engine`` is ``None`` so test runs don't accumulate idle
    connection pools.
    """
    orch, _ = make_inmem_orchestrator()
    app = create_app(orchestrator=orch)
    assert app.state.engine is None
    assert app.state.orchestrator is orch


def test_create_app_without_database_url_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production guardrail: no orchestrator + no DB URL → fail loud.

    The conftest autouse sets a stub ``REPOPULSE_DATABASE_URL`` so we
    explicitly delete it for this test. Re-reading is critical:
    ``Settings`` reads the env var at construction time, and
    ``create_app`` calls ``Settings()`` itself.
    """
    monkeypatch.delenv("REPOPULSE_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="REPOPULSE_DATABASE_URL is unset"):
        create_app()


def test_create_app_with_database_url_builds_engine_and_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production path: a configured DB URL produces an engine + sessionmaker
    + an async :class:`PipelineOrchestrator` ready to receive requests.

    The engine is **lazy** — it never dials the stub URL on construction.
    """
    from repopulse.pipeline.async_orchestrator import (
        PipelineOrchestrator as AsyncPipelineOrchestrator,
    )

    monkeypatch.setenv(
        "REPOPULSE_DATABASE_URL",
        "postgresql+psycopg://stub:stub@localhost:1/stub",
    )
    app = create_app()
    assert app.state.engine is not None
    assert isinstance(app.state.orchestrator, AsyncPipelineOrchestrator)


def test_lifespan_disposes_engine_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lifespan finally-block awaits ``engine.dispose()`` on shutdown.

    ``AsyncEngine.dispose`` is read-only on the SQLAlchemy class so we
    swap the whole ``app.state.engine`` for an ``AsyncMock``-shaped stub
    that exposes ``dispose()`` we can assert on. The lifespan reads
    ``engine`` from a closure captured during ``create_app``; the new
    ``main.py`` re-reads through ``app.state.engine`` to make this swap
    observable.
    """
    monkeypatch.setenv(
        "REPOPULSE_DATABASE_URL",
        "postgresql+psycopg://stub:stub@localhost:1/stub",
    )
    app = create_app()
    assert app.state.engine is not None

    # Replace the closure-captured engine via the patched module-level
    # AsyncEngine.dispose. Since the lifespan calls
    # ``await engine.dispose()`` on the closure variable, the simplest
    # observable seam is patching the class method.
    with patch(
        "sqlalchemy.ext.asyncio.AsyncEngine.dispose",
        new_callable=AsyncMock,
    ) as dispose_mock:
        with TestClient(app) as _:
            pass  # entering + exiting triggers lifespan shutdown
    dispose_mock.assert_awaited()

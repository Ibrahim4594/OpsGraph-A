"""Shared fixtures for the integration test suite (M2.0 task 10).

Integration tests are marked ``@pytest.mark.integration`` and excluded
from the default unit gate. They run via:

    pytest -m integration -q

They need Docker (Testcontainers Postgres) — without it, every test in
this folder skips with a clear message. CI runs them in the dedicated
``integration`` job.

Hermeticity strategy
--------------------

- **Session-scoped Postgres container** — one container per pytest run.
  Spinning up a fresh container per test would dominate runtime; one
  container with per-test data wipes is cheap and equivalent.
- **Schema created once** — ``alembic upgrade head`` runs at session
  start so every test sees a fully-migrated DB.
- **Per-test ``TRUNCATE ... CASCADE``** — the autouse
  ``_clean_tables_between_tests`` fixture wipes every table before each
  test. Sub-millisecond on empty tables; the CASCADE handles bridge
  tables.
- **Per-test ``async_sessionmaker``** — a fresh ``AsyncEngine`` and
  ``async_sessionmaker`` are constructed per test so connection-pool
  state can't leak between tests.

The repo tests open sessions directly via the session_maker; the
orchestrator integration test passes the session_maker into a real
:class:`PipelineOrchestrator`.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        r = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            timeout=5,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except (subprocess.TimeoutExpired, OSError):
        return False


_INTEGRATION_FOLDER = "tests/integration"


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip integration tests if Docker isn't reachable.

    Scope is **only** items under ``tests/integration/`` — without that
    guard the hook would fire for every test in the suite.
    """
    _ = config
    if _docker_available():
        return
    skip_reason = pytest.mark.skip(
        reason="Docker daemon not reachable; integration tests need Testcontainers Postgres.",
    )
    for item in items:
        node_path = str(item.path).replace("\\", "/")
        if _INTEGRATION_FOLDER not in node_path:
            continue
        item.add_marker(skip_reason)


def _alembic_root() -> Path:
    """Return the ``backend/`` directory so alembic CWD is correct."""
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """Spin up a session-scoped Postgres 16 container; run migrations once.

    Yields the SQLAlchemy URL with the ``+psycopg`` driver. The container
    is torn down when the session ends.
    """
    from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]

    with PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url()
        url = url.replace("+psycopg2", "+psycopg")
        if "+psycopg" not in url:
            url = url.replace("postgresql://", "postgresql+psycopg://")

        # Run alembic upgrade head once against the fresh DB.
        env = {
            **os.environ,
            "REPOPULSE_DATABASE_URL": url,
        }
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            cwd=str(_alembic_root()),
            env=env,
        )
        if result.returncode != 0:
            pytest.fail(
                f"alembic upgrade head failed (session setup):\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )

        yield url


@pytest.fixture
async def engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    """Per-test ``AsyncEngine`` over the session-scoped container.

    A fresh engine per test keeps connection-pool state from leaking
    across tests. The engine is disposed in finally.
    """
    eng = create_async_engine(
        postgres_url,
        future=True,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=2,
    )
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.fixture
def session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine, expire_on_commit=False, autoflush=False, class_=AsyncSession
    )


# Tables in CASCADE-safe order. We TRUNCATE everything in one statement
# with CASCADE so dependency order doesn't matter, but listing them
# explicitly catches new tables that forget to land here.
_TABLES = (
    "raw_events",
    "normalized_events",
    "anomalies",
    "incidents",
    "incident_events",
    "incident_anomalies",
    "recommendations",
    "recommendation_transitions",
    "action_history",
    "workflow_usage",
)


@pytest.fixture(autouse=True)
def _clean_tables_between_tests(postgres_url: str) -> Iterator[None]:
    """Wipe every test row before each test runs (autouse).

    Sync engine + ``TRUNCATE ... RESTART IDENTITY CASCADE`` is the
    fastest path: empty-table TRUNCATE is sub-millisecond and CASCADE
    handles the bridge-table FKs without us having to compute order.
    """
    sync_engine = create_engine(postgres_url, future=True)
    try:
        with sync_engine.begin() as conn:
            stmt = (
                f"TRUNCATE TABLE {', '.join(_TABLES)} "
                "RESTART IDENTITY CASCADE"
            )
            conn.execute(text(stmt))
        yield
    finally:
        sync_engine.dispose()

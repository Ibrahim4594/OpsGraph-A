"""Shared fixtures for the migration test suite (M2.0 task 7).

Migration tests are marked ``@pytest.mark.migration`` and excluded from
the default unit gate. They run via:

    pytest -m migration -q

They need Docker (Testcontainers Postgres) — without it, every test in
this folder skips with a clear message. CI provides Docker via the
``services: postgres`` block in ``.github/workflows/migrations.yml``.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest


def _docker_available() -> bool:
    """Return True iff a Docker daemon is reachable.

    We don't care which OS the daemon runs on, only that
    ``docker version --format '{{.Server.Version}}'`` exits 0 within a
    couple of seconds. ``shutil.which`` first so we don't shell out
    for a non-existent binary.
    """
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


@pytest.fixture(scope="session")
def docker_available() -> bool:
    return _docker_available()


_MIGRATION_FOLDER = "tests/migrations"


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip migration tests if Docker isn't reachable.

    Scope is **only** items under ``tests/migrations/`` — without that
    guard this conftest's hook would fire for every test in the suite
    (pytest invokes ``pytest_collection_modifyitems`` from every
    discovered conftest, regardless of the test's own location). Tests
    opt out by applying ``@pytest.mark.no_docker`` — used by the offline
    SQL-emit smoke test that runs without a running daemon.
    """
    _ = config
    if _docker_available():
        return
    skip_reason = pytest.mark.skip(
        reason="Docker daemon not reachable; migration tests need Testcontainers Postgres.",
    )
    for item in items:
        node_path = str(item.path).replace("\\", "/")
        if _MIGRATION_FOLDER not in node_path:
            continue
        if any(m.name == "no_docker" for m in item.iter_markers()):
            continue
        item.add_marker(skip_reason)


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[str]:
    """Spin up an ephemeral Postgres 16 container and yield its DSN.

    Session-scoped so the migration tests share a container; each test
    runs migrations on a freshly-truncated DB (see ``clean_db`` fixture).
    """
    from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]

    with PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url()
        # Testcontainers returns ``postgresql+psycopg2://...`` by default;
        # rewrite to the psycopg3 driver our app uses.
        url = url.replace("+psycopg2", "+psycopg")
        if "+psycopg" not in url:
            url = url.replace("postgresql://", "postgresql+psycopg://")
        yield url


@pytest.fixture
def clean_db(postgres_container: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Yield a clean DB URL: drop and recreate ``public`` schema between tests.

    Sets ``REPOPULSE_DATABASE_URL`` so the Alembic ``env.py`` and any
    in-process consumer (CLI invocations) read the same URL.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(postgres_container, future=True)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    monkeypatch.setenv("REPOPULSE_DATABASE_URL", postgres_container)
    yield postgres_container


def _alembic_root() -> Path:
    """Resolve the ``backend/`` dir so subprocess CWD is correct.

    Invoked from ``tests/migrations/`` — go up two levels.
    """
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def alembic_cwd() -> Path:
    return _alembic_root()


@pytest.fixture(autouse=True)
def _ensure_database_url_unset_outside_session() -> Iterator[None]:
    """Clear ``REPOPULSE_DATABASE_URL`` before each test that doesn't
    explicitly set it via ``clean_db`` — keeps tests order-independent.

    The ``conftest.py`` at the suite root sets a stub URL; we reset it
    here so a migration test that forgets to use ``clean_db`` fails
    loudly instead of silently dialling the stub.
    """
    saved = os.environ.pop("REPOPULSE_DATABASE_URL", None)
    try:
        yield
    finally:
        if saved is not None:
            os.environ["REPOPULSE_DATABASE_URL"] = saved

"""Async engine + sessionmaker factories for the storage layer (M2.0).

Design rules (per the M2.0 plan):

- **No module-level state.** Every function returns a fresh object so unit
  tests can construct, dispose, and re-construct without leaking
  connections between cases.
- **Lazy.** Constructing an :class:`AsyncEngine` does **not** open a
  network connection — SQLAlchemy connects on first ``.connect()`` /
  ``.begin()``. So tests can build an engine against a stub URL without
  Docker; only integration tests (Testcontainers) actually open sockets.
- **Settings-aware convenience.** :func:`make_engine_from_settings` reads
  ``Settings.database_url`` and raises a clear ``RuntimeError`` if unset —
  the same fail-loud pattern used by ``migrations/env.py``.

Repositories (M2.0 task 4) and the orchestrator facade (task 5) consume
the ``async_sessionmaker`` returned by :func:`make_session_factory`. The
FastAPI app (task 6) holds the sessionmaker on ``app.state`` and yields
sessions through a dependency — but that wiring is **not** in this file.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from repopulse.config import Settings


def make_engine(
    url: str,
    *,
    pool_size: int = 5,
    max_overflow: int = 10,
    echo: bool = False,
) -> AsyncEngine:
    """Create an :class:`AsyncEngine` for ``url``.

    Returns immediately without connecting. Pool parameters default to the
    Settings defaults; tests can override.
    """
    if not url:
        raise RuntimeError(
            "database URL is empty — cannot build an engine. Set "
            "REPOPULSE_DATABASE_URL or pass an explicit URL."
        )
    return create_async_engine(
        url,
        future=True,
        echo=echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
    )


def make_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Build an ``async_sessionmaker`` bound to ``engine``.

    ``expire_on_commit=False`` matches our repository pattern: domain
    dataclasses are constructed from ORM rows inside the repo and
    returned to the caller; the caller never re-reads attributes on the
    ORM instance after commit.
    """
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
        class_=AsyncSession,
    )


def make_engine_from_settings(settings: Settings) -> AsyncEngine:
    """Convenience: pull URL + pool config from a :class:`Settings` instance.

    Raises ``RuntimeError`` if ``settings.database_url`` is unset, matching
    the fail-loud pattern in ``migrations/env.py``.
    """
    if not settings.database_url:
        raise RuntimeError(
            "Settings.database_url is unset. Set REPOPULSE_DATABASE_URL "
            "before calling code paths that require the storage layer."
        )
    return make_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_pool_max_overflow,
    )

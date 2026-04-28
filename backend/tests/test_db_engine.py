"""Unit tests for the engine + session factories (M2.0 task 2).

These run without Docker / Postgres. They verify factory shape only;
integration tests under ``tests/integration/`` (M2.0 task 10) will exercise
the engine against a real Testcontainers Postgres.
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from repopulse.config import Settings
from repopulse.db.base import Base, metadata
from repopulse.db.engine import (
    make_engine,
    make_engine_from_settings,
    make_session_factory,
)


def test_metadata_has_naming_convention() -> None:
    """All constraint/index names should be derived deterministically."""
    naming = metadata.naming_convention
    assert naming["ix"] == "ix_%(column_0_label)s"
    assert naming["uq"] == "uq_%(table_name)s_%(column_0_name)s"
    assert naming["fk"] == (
        "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
    )
    assert naming["pk"] == "pk_%(table_name)s"


def test_base_uses_shared_metadata() -> None:
    assert Base.metadata is metadata


def test_make_engine_returns_async_engine_without_connecting() -> None:
    """Engine construction is lazy — no socket opened, no Docker needed."""
    engine = make_engine("postgresql+psycopg://stub:stub@localhost:1/stub")
    assert isinstance(engine, AsyncEngine)
    # Engine should report the right dialect even without a live connection.
    assert engine.dialect.name == "postgresql"


def test_make_engine_rejects_empty_url() -> None:
    with pytest.raises(RuntimeError, match="empty"):
        make_engine("")


def test_make_session_factory_binds_to_engine() -> None:
    engine = make_engine("postgresql+psycopg://stub:stub@localhost:1/stub")
    factory = make_session_factory(engine)
    assert isinstance(factory, async_sessionmaker)
    # The factory's bind should be the engine we passed.
    session = factory()
    try:
        assert session.bind is engine
        # Sanity: it's the right session class.
        assert isinstance(session, AsyncSession)
    finally:
        # ``close`` on an AsyncSession that never connected is safe.
        # We don't await it — there's no event loop here, and no
        # connection was opened.
        pass


def test_make_engine_from_settings_uses_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "REPOPULSE_DATABASE_URL",
        "postgresql+psycopg://x:y@localhost:1/z",
    )
    settings = Settings()
    engine = make_engine_from_settings(settings)
    assert isinstance(engine, AsyncEngine)
    assert engine.dialect.name == "postgresql"


def test_make_engine_from_settings_raises_when_url_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REPOPULSE_DATABASE_URL", raising=False)
    settings = Settings()
    assert settings.database_url is None
    with pytest.raises(RuntimeError, match="database_url is unset"):
        make_engine_from_settings(settings)


def test_settings_database_url_is_optional_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Booting Settings without REPOPULSE_DATABASE_URL is allowed.

    This preserves v1.1's test-friendly default — unit tests should not
    need Postgres just to instantiate Settings.
    """
    monkeypatch.delenv("REPOPULSE_DATABASE_URL", raising=False)
    settings = Settings()
    assert settings.database_url is None
    # Defaults from the Settings class.
    assert settings.database_pool_size == 5
    assert settings.database_pool_max_overflow == 10

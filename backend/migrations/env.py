"""Alembic environment for the RepoPulse storage layer (M2.0).

This file:

1. Reads the database URL from ``REPOPULSE_DATABASE_URL`` (no hard-coded
   fallback — fail loudly if unset, matching the v1.1 fail-closed pattern
   for ``REPOPULSE_API_SHARED_SECRET``).
2. Imports the SQLAlchemy ``MetaData`` from :mod:`repopulse.db.base` so
   ``alembic revision --autogenerate`` can compare against the live
   schema. The ``base`` module ships in M2.0 task 2; until then the
   import is wrapped so this file stays *valid* (Alembic CLI smoke test
   passes) without needing the model layer.
3. Supports both online (real DB connection) and offline (SQL emit only)
   modes. We use online in CI + dev; offline is reserved for "show me the
   SQL" reviews.

Migrations themselves do **not** import ``repopulse.db.*`` — they use raw
``op.create_table`` / ``op.add_column`` calls so a downgrade can run even
if the model layer has been refactored. This keeps each revision a
self-contained, auditable artefact.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _database_url() -> str:
    url = os.environ.get("REPOPULSE_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "REPOPULSE_DATABASE_URL is not set. Alembic refuses to run with "
            "an unspecified database URL — set it in the environment "
            "(see docs/SETUP.md for the dev value)."
        )
    return url


# Try to load the SQLAlchemy MetaData for autogenerate. Falls back to None
# until M2.0 task 2 lands ``repopulse.db.base``; CLI smoke (``alembic heads``)
# still works because target_metadata=None is supported.
try:
    from repopulse.db.base import metadata as target_metadata  # type: ignore[import-not-found]
except ImportError:
    target_metadata = None


def run_migrations_offline() -> None:
    """Render SQL without a live connection — useful for reviewing diffs."""
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Open a sync connection (psycopg) and run migrations."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

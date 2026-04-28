"""SQLAlchemy declarative base + shared MetaData (M2.0).

The :data:`metadata` object holds the explicit naming convention for all
constraints/indexes so Alembic-generated names are stable across
environments and reviewable in PRs. The convention follows the SQLAlchemy
docs verbatim — short keys, deterministic order.

ORM models declared in :mod:`repopulse.db.models.*` inherit from
:class:`Base`, which wires their ``__tablename__``-derived classes into
this metadata. Migrations target the same metadata via
``backend/migrations/env.py``::

    from repopulse.db.base import metadata as target_metadata

This module is **import-safe** with no database dependency: nothing here
opens a connection or reads ``REPOPULSE_DATABASE_URL``.
"""
from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

#: Shared MetaData with the explicit naming convention. Imported by
#: ``migrations/env.py`` for autogenerate diffs and by every ORM model
#: defined in :mod:`repopulse.db.models`.
metadata: MetaData = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Project-wide declarative base. All ORM models inherit from this."""

    metadata = metadata

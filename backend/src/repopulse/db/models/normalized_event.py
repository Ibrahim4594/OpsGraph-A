"""``normalized_events`` — the post-``normalize()`` shape persisted 1:1 with ``raw_events``.

The relationship is **strict 1:1**: every raw event produces exactly one
normalized event with the same ``event_id``. We model that with a shared PK
that is also a FK back to ``raw_events.event_id``. This rules out
"normalized without raw" rows that would shadow the dedup anchor.

The ``severity`` column carries the v1.1 ``Severity`` literal
(info / warning / error / critical). Stored as a short ``String`` with a
CHECK constraint rather than a Postgres ENUM because adding a new band
later (e.g. M3.0 introduces ``debug``) becomes a one-line CHECK migration
instead of an ``ALTER TYPE`` dance.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from repopulse.db.base import Base

#: Allowed values for ``normalized_events.severity``. Mirrors
#: ``repopulse.pipeline.normalize.Severity``.
SEVERITY_VALUES: tuple[str, ...] = ("info", "warning", "error", "critical")


class NormalizedEventORM(Base):
    """Normalised event row. PK + FK = ``raw_events.event_id``."""

    __tablename__ = "normalized_events"

    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("raw_events.event_id", ondelete="CASCADE"),
        primary_key=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    __table_args__ = (
        CheckConstraint(
            "severity IN ('info','warning','error','critical')",
            name="severity_in_set",
        ),
        # Hot path: SLO + correlation queries scan by received_at + occurred_at.
        Index("ix_normalized_events_received_at", "received_at"),
        Index("ix_normalized_events_occurred_at", "occurred_at"),
    )

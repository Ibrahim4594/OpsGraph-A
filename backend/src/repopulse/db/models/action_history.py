"""``action_history`` — operator + system audit feed.

Persistent equivalent of the v1.1 bounded ``deque[ActionHistoryEntry]``
on the orchestrator. Entries:
- ``approve`` / ``reject``: written when an operator transitions a
  recommendation. ``recommendation_id`` is set.
- ``observe``: written when R1 fallback auto-observes. ``actor`` is
  ``"system"``; ``recommendation_id`` is set.
- ``workflow-run``: written when a GitHub agentic workflow run ingests
  via ``POST /api/v1/github/usage``. ``recommendation_id`` may be NULL
  (workflow runs are not always tied to a single recommendation).

Behavior change from v1.1: rows persist forever — the ``maxlen=200``
deque cap is gone. The dashboard's GET keeps its ``LIMIT`` parameter so
the page feels identical; a retention job (M3.2) prunes by ``at``.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from repopulse.db.base import Base

#: Allowed values for ``action_history.kind``.
ACTION_KIND_VALUES: tuple[str, ...] = (
    "approve",
    "reject",
    "observe",
    "workflow-run",
)


class ActionHistoryORM(Base):
    __tablename__ = "action_history"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    recommendation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("recommendations.recommendation_id", ondelete="SET NULL"),
        nullable=True,
    )
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (
        CheckConstraint(
            "kind IN ('approve','reject','observe','workflow-run')",
            name="kind_in_set",
        ),
        # Dashboard "newest first" feed query.
        Index("ix_action_history_at", "at"),
        # Filter chips on the dashboard: WHERE kind = ?
        Index("ix_action_history_kind", "kind"),
    )

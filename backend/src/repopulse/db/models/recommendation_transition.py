"""``recommendation_transitions`` — append-only audit of state changes.

Every successful ``approve`` / ``reject`` / auto-``observe`` transition
writes a row here. The ``recommendations.state`` column carries the
*current* state; this table carries the *history* of how it got there.

Rows are never updated or deleted in normal operation. A future retention
job (M3.2 ops runbooks) may prune by ``at < now() - retention``.

Design tradeoffs:
- Surrogate ``id UUID`` PK (rows have no natural identity).
- ``from_state`` and ``to_state`` are independent CHECK-constrained
  String(16) columns; we don't compose a single "transition" enum because
  legal transitions are policy that lives in the orchestrator, not the DB.
- ``actor`` is plain text (matches the v1.1 ``Settings.api_operator_actor``
  pattern); JWT-derived identity in M3.0 still writes a string here.
- ``reason`` is nullable — approvals don't carry a reason; rejections may.
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


class RecommendationTransitionORM(Base):
    __tablename__ = "recommendation_transitions"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    recommendation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("recommendations.recommendation_id", ondelete="CASCADE"),
        nullable=False,
    )
    from_state: Mapped[str] = mapped_column(String(16), nullable=False)
    to_state: Mapped[str] = mapped_column(String(16), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "from_state IN ('pending','approved','rejected','observed')",
            name="from_state_in_set",
        ),
        CheckConstraint(
            "to_state IN ('pending','approved','rejected','observed')",
            name="to_state_in_set",
        ),
        # Audit query: WHERE recommendation_id = ? ORDER BY at.
        Index(
            "ix_recommendation_transitions_rec_at",
            "recommendation_id",
            "at",
        ),
    )

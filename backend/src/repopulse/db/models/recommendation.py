"""``recommendations`` — the ranked output of ``recommend()``.

Three enum-like columns (``state``, ``action_category``, ``risk_level``)
all use ``String`` + CHECK so a future enum value addition is a one-line
ALTER. The dashboard inbox query is heavy on
``WHERE state = 'pending' ORDER BY confidence DESC`` so we add
``(state, action_category)`` as a compound index.

``evidence_trace`` is a tuple of strings in the domain; we persist it as
a JSONB array. Average size is small (1–10 lines, under 1 KB), so a
single-column JSONB read is cheaper than a child table.

The v1.1 ``_rec_state`` overlay dict goes away — the ``state`` column
*is* the source of truth post-M2.0. Transitions go through
``recommendation_transitions`` (separate model).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from repopulse.db.base import Base

#: Allowed action categories. Mirrors
#: :data:`repopulse.recommend.engine.ActionCategory`.
ACTION_CATEGORY_VALUES: tuple[str, ...] = (
    "observe",
    "triage",
    "escalate",
    "rollback",
)

#: Allowed risk levels.
RISK_LEVEL_VALUES: tuple[str, ...] = ("low", "medium", "high")

#: Allowed recommendation states. Mirrors
#: :data:`repopulse.recommend.engine.State`.
STATE_VALUES: tuple[str, ...] = ("pending", "approved", "rejected", "observed")


class RecommendationORM(Base):
    __tablename__ = "recommendations"

    recommendation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True
    )
    incident_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.incident_id", ondelete="CASCADE"),
        nullable=False,
    )
    action_category: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_trace: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )

    __table_args__ = (
        CheckConstraint(
            "action_category IN ('observe','triage','escalate','rollback')",
            name="action_category_in_set",
        ),
        CheckConstraint(
            "risk_level IN ('low','medium','high')",
            name="risk_level_in_set",
        ),
        CheckConstraint(
            "state IN ('pending','approved','rejected','observed')",
            name="state_in_set",
        ),
        # Inbox query: WHERE state = 'pending' ORDER BY confidence DESC.
        Index(
            "ix_recommendations_state_action_category",
            "state",
            "action_category",
        ),
        Index("ix_recommendations_incident_id", "incident_id"),
    )

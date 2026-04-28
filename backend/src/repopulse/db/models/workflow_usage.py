"""``workflow_usage`` — agentic GitHub workflow run telemetry.

One row per ``POST /api/v1/github/usage``. The natural key is
``(repository, run_id)`` — GitHub guarantees ``run_id`` is unique within
a repository — so we declare it as a UNIQUE constraint and use a
surrogate ``id UUID`` PK so future joins remain cheap.

The v1.1 :class:`repopulse.github.usage.WorkflowUsage` carries
``cost_estimate_usd`` derived from the static rate table; we persist it
here so the dashboard and reports can aggregate without recomputing.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from repopulse.db.base import Base


class WorkflowUsageORM(Base):
    __tablename__ = "workflow_usage"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_name: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    conclusion: Mapped[str] = mapped_column(String(32), nullable=False)
    repository: Mapped[str] = mapped_column(String(255), nullable=False)
    cost_estimate_usd: Mapped[float] = mapped_column(Float, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        # Idempotency: GitHub run_id is unique per repository.
        UniqueConstraint(
            "run_id", "repository", name="run_id_repository"
        ),
        # Dashboard cost-by-time queries.
        Index("ix_workflow_usage_received_at", "received_at"),
        Index(
            "ix_workflow_usage_repository_workflow",
            "repository",
            "workflow_name",
        ),
    )

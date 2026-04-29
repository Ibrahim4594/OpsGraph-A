"""``incidents`` + bridge tables ``incident_events`` + ``incident_anomalies``.

The v1.1 :class:`repopulse.correlation.engine.Incident` carries
``incident_id`` natively, so it becomes the PK directly. ``sources`` is a
small, ordered tuple of strings — stored as a JSONB array; queries that
need source membership go through the bridge table joined onto
``normalized_events``.

``signature_hash`` is the persistent equivalent of v1.1's in-memory
``PipelineOrchestrator._seen_keys`` LRU set. It is a deterministic hash
of ``(frozenset[event_id], frozenset[(timestamp, value, series_name)])``
— the same content signature defined in
:func:`repopulse.pipeline.orchestrator._incident_key`. The UNIQUE
constraint enforces "same content → same row," so re-evaluating an
overlapping window does not produce duplicate recommendations.

It is declared **here** (not in migration 0005) per the v2.0 plan refresh
2026-04-29: the model is the source of truth, migration 0005 only
performs the DDL needed for existing deployments (ADD COLUMN + backfill
+ UNIQUE INDEX). Fresh databases (CI, dev) get the column from migration
0001 directly, no special-casing.

The two bridge tables are plain :class:`Table` objects (not classes)
because they have no behaviour beyond the join — composite PKs, FKs, and
ON DELETE CASCADE so deleting an incident cleans up its associations.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from repopulse.db.base import Base, metadata


class IncidentORM(Base):
    __tablename__ = "incidents"

    incident_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    sources: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    # SHA-256 hex digest (64 chars) of the incident's content signature.
    signature_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        # Time-range queries on the dashboard incidents page.
        Index("ix_incidents_started_at", "started_at"),
        Index("ix_incidents_ended_at", "ended_at"),
        UniqueConstraint("signature_hash", name="signature_hash"),
    )


# Plain Table: many-to-many bridge from incidents to normalized_events.
# An event can belong to at most one incident (correlate() does not
# overlap), but storing it as M2M leaves room for that constraint to
# relax later (e.g. multi-window correlation) without a schema change.
incident_events = Table(
    "incident_events",
    metadata,
    Column(
        "incident_id",
        PGUUID(as_uuid=True),
        ForeignKey("incidents.incident_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "event_id",
        PGUUID(as_uuid=True),
        ForeignKey("normalized_events.event_id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


# Plain Table: many-to-many bridge from incidents to anomalies.
incident_anomalies = Table(
    "incident_anomalies",
    metadata,
    Column(
        "incident_id",
        PGUUID(as_uuid=True),
        ForeignKey("incidents.incident_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "anomaly_id",
        PGUUID(as_uuid=True),
        ForeignKey("anomalies.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

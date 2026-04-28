"""``raw_events`` — the idempotency anchor for inbound ingest.

Persisted **before** normalization runs so a duplicate ``EventEnvelope``
post (same ``event_id``) is rejected at the DB layer via the PK uniqueness,
not by an in-memory dedup set. This is the v1.1 → v2.0 migration of
``PipelineOrchestrator._seen_keys`` for the per-event side of dedup.

Storage notes:
- ``payload`` is :class:`postgresql.JSONB` so we can index inside the JSON
  later if needed without a schema change.
- ``received_at`` is the wall-clock ingest time; the request handler sets
  it. ``occurred_at`` is the event's logical time, when known (mapped from
  the OTel/GitHub source). They are the same value for synchronous,
  in-process ingest.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from repopulse.db.base import Base


class RawEventORM(Base):
    """Raw ingested event, pre-normalisation.

    ``event_id`` is the PK and the idempotency anchor — duplicate POSTs
    with the same id collide with the PK and are rejected with an
    ``INSERT ... ON CONFLICT DO NOTHING`` no-op at the repo layer.
    """

    __tablename__ = "raw_events"

    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

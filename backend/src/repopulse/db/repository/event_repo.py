"""Event repository — owns ``raw_events`` + ``normalized_events``.

The two tables share a 1:1 PK by design (see ORM model docstrings). They
live behind a single repo because every ingest writes both, and the
caller (orchestrator) wants one abstraction for "persist this event."

Idempotency: :meth:`EventRepository.insert_raw_idempotent` is the v1.1
``_seen_keys`` per-event side, lifted into the database. A duplicate
``event_id`` POST collides with the PK and the method returns ``False``;
the orchestrator then skips normalize / detect for that event.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from repopulse.api.events import EventEnvelope
from repopulse.db.models.normalized_event import NormalizedEventORM
from repopulse.db.models.raw_event import RawEventORM
from repopulse.pipeline.normalize import NormalizedEvent, Severity


def _to_normalized_domain(orm: NormalizedEventORM) -> NormalizedEvent:
    """Map a ``NormalizedEventORM`` row to a domain :class:`NormalizedEvent`.

    ``attributes`` is JSONB on the DB side (``dict[str, Any]``) but the
    domain dataclass declares ``dict[str, str]``. The ingest pipeline
    flattens to strings already (see ``normalize._flatten_attributes``)
    so the cast is safe — it is documented as an invariant of the
    normalize step, not a runtime check.
    """
    return NormalizedEvent(
        event_id=orm.event_id,
        received_at=orm.received_at,
        occurred_at=orm.occurred_at,
        source=orm.source,
        kind=orm.kind,
        severity=orm.severity,  # type: ignore[arg-type]
        attributes=dict(orm.attributes),
    )


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_raw_idempotent(
        self,
        envelope: EventEnvelope,
        *,
        received_at: datetime,
        occurred_at: datetime,
    ) -> bool:
        """Persist the raw envelope; return ``True`` iff a new row landed.

        Uses ``ON CONFLICT (event_id) DO NOTHING RETURNING event_id`` —
        the PK is the idempotency anchor. The caller MUST treat ``False``
        as "duplicate, skip pipeline" to preserve v1.1 semantics.
        """
        payload = envelope.payload if isinstance(envelope.payload, dict) else {}
        stmt = (
            pg_insert(RawEventORM)
            .values(
                event_id=envelope.event_id,
                source=envelope.source,
                kind=envelope.kind,
                payload=payload,
                received_at=received_at,
                occurred_at=occurred_at,
            )
            .on_conflict_do_nothing(index_elements=["event_id"])
            .returning(RawEventORM.event_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def insert_normalized(self, event: NormalizedEvent) -> None:
        """Persist a normalized event. PK = FK = ``raw_events.event_id``."""
        self._session.add(
            NormalizedEventORM(
                event_id=event.event_id,
                received_at=event.received_at,
                occurred_at=event.occurred_at,
                source=event.source,
                kind=event.kind,
                severity=event.severity,
                attributes=dict(event.attributes),
            )
        )

    async def list_recent_normalized(
        self,
        *,
        limit: int = 1000,
    ) -> list[NormalizedEvent]:
        """Return up to ``limit`` most-recent normalised events, oldest-first.

        Mirrors v1.1's ``deque[maxlen=1000]`` order: ``correlate()``
        expects oldest-first because it folds anomalies + events into a
        single sorted timeline.
        """
        if limit < 0:
            raise ValueError(f"limit must be >= 0, got {limit!r}")
        stmt = (
            select(NormalizedEventORM)
            .order_by(NormalizedEventORM.received_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars())
        return [_to_normalized_domain(r) for r in reversed(rows)]


__all__ = ["EventRepository", "Severity"]

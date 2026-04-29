"""Incident repository — owns ``incidents`` + the two bridge tables.

The dedup-by-content invariant is enforced by the DB:
``ON CONFLICT (signature_hash) DO NOTHING RETURNING incident_id``. The
caller (T5 orchestrator) computes ``signature_hash`` from
``_incident_key(incident)`` (SHA-256 hex of the same content tuple v1.1
already used in-memory) and passes it in. If no row is returned, the
content has already produced an incident; the orchestrator skips
recommendation emission for it.

Bridge rows (``incident_events``, ``incident_anomalies``) are inserted in
the same transaction so an incident is never half-linked.
"""
from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from repopulse.correlation.engine import Incident
from repopulse.db.models.incident import (
    IncidentORM,
    incident_anomalies,
    incident_events,
)


def _to_incident_domain(orm: IncidentORM) -> Incident:
    """Map an ``IncidentORM`` row to a domain :class:`Incident` shell.

    The bridge tables are NOT walked here — the resulting :class:`Incident`
    has empty ``events`` / ``anomalies`` tuples. The orchestrator usually
    re-correlates from current event/anomaly state rather than reloading
    fully linked incidents, so this shallow read is the common case.
    A future "load fully" method can join through the bridges when a
    detail page needs it.
    """
    return Incident(
        incident_id=orm.incident_id,
        started_at=orm.started_at,
        ended_at=orm.ended_at,
        sources=tuple(orm.sources),
        anomalies=(),
        events=(),
    )


class IncidentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_with_signature(
        self,
        incident: Incident,
        *,
        signature_hash: str,
        anomaly_ids: Sequence[UUID],
    ) -> bool:
        """Persist ``incident`` + its bridges; return ``True`` iff inserted.

        ``False`` means the ``signature_hash`` already exists → the
        orchestrator must NOT emit a recommendation, matching v1.1's
        behavior where ``_register_key`` returned ``False`` for repeats.

        Bridge rows are inserted only on success — a duplicate signature
        means the original incident's bridges are already in place.
        """
        stmt = (
            pg_insert(IncidentORM)
            .values(
                incident_id=incident.incident_id,
                started_at=incident.started_at,
                ended_at=incident.ended_at,
                sources=list(incident.sources),
                signature_hash=signature_hash,
            )
            .on_conflict_do_nothing(index_elements=["signature_hash"])
            .returning(IncidentORM.incident_id)
        )
        result = await self._session.execute(stmt)
        if result.scalar_one_or_none() is None:
            return False

        if incident.events:
            await self._session.execute(
                incident_events.insert(),
                [
                    {
                        "incident_id": incident.incident_id,
                        "event_id": e.event_id,
                    }
                    for e in incident.events
                ],
            )
        if anomaly_ids:
            await self._session.execute(
                incident_anomalies.insert(),
                [
                    {
                        "incident_id": incident.incident_id,
                        "anomaly_id": aid,
                    }
                    for aid in anomaly_ids
                ],
            )
        return True

    async def list_recent(self, *, limit: int = 100) -> list[Incident]:
        """Return up to ``limit`` most-recent incidents, newest-first.

        Mirrors v1.1's ``latest_incidents`` ordering. Returns shallow
        :class:`Incident` shells (see :func:`_to_incident_domain`).
        """
        if limit < 0:
            raise ValueError(f"limit must be >= 0, got {limit!r}")
        stmt = (
            select(IncidentORM)
            .order_by(IncidentORM.ended_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [_to_incident_domain(r) for r in result.scalars()]


__all__ = ["IncidentRepository"]

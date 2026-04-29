"""Anomaly repository — owns ``anomalies``.

The domain :class:`Anomaly` is anonymous (no id field). The DB row has a
surrogate UUID ``id`` PK. :meth:`insert_many` mints those UUIDs and
returns them in the same order as the input so the orchestrator can use
the IDs to populate the ``incident_anomalies`` bridge during incident
persistence.
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repopulse.anomaly.detector import Anomaly
from repopulse.db.models.anomaly import AnomalyORM


def _to_anomaly_domain(orm: AnomalyORM) -> Anomaly:
    return Anomaly(
        timestamp=orm.timestamp,
        value=orm.value,
        baseline_median=orm.baseline_median,
        baseline_mad=orm.baseline_mad,
        score=orm.score,
        severity=orm.severity,  # type: ignore[arg-type]
        series_name=orm.series_name,
    )


class AnomalyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_many(self, anomalies: Sequence[Anomaly]) -> list[UUID]:
        """Persist a batch of anomalies. Returns the minted IDs in input order.

        The IDs are minted client-side (``uuid4``) so the caller has them
        before the session flushes — the orchestrator immediately uses
        them to build ``incident_anomalies`` bridge rows in the same
        transaction.
        """
        out: list[UUID] = []
        for a in anomalies:
            anomaly_id = uuid.uuid4()
            self._session.add(
                AnomalyORM(
                    id=anomaly_id,
                    timestamp=a.timestamp,
                    value=a.value,
                    baseline_median=a.baseline_median,
                    baseline_mad=a.baseline_mad,
                    score=a.score,
                    severity=a.severity,
                    series_name=a.series_name,
                )
            )
            out.append(anomaly_id)
        return out

    async def list_recent_with_ids(
        self,
        *,
        limit: int = 200,
    ) -> list[tuple[UUID, Anomaly]]:
        """Return up to ``limit`` most-recent anomalies, oldest-first, paired
        with their DB IDs.

        IDs are needed so the orchestrator can wire ``incident_anomalies``
        bridges when correlate() groups these into incidents.
        """
        if limit < 0:
            raise ValueError(f"limit must be >= 0, got {limit!r}")
        stmt = (
            select(AnomalyORM)
            .order_by(AnomalyORM.timestamp.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars())
        return [(r.id, _to_anomaly_domain(r)) for r in reversed(rows)]


__all__ = ["AnomalyRepository"]

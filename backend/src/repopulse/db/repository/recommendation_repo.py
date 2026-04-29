"""Recommendation repository — owns ``recommendations`` + the transition log.

:meth:`update_state` writes BOTH the state column on ``recommendations``
AND a row to ``recommendation_transitions`` in the same call. The caller
holds the session open across the whole transition (incl. the
``action_history`` row that the orchestrator adds), so a partial transition
cannot be observed.

Pending → approved | rejected is the only legal forward transition.
``observed`` is set at insert time by the recommend engine for R1
fallback. We refuse to transition ``observed`` rows here — that policy
is duplicated from v1.1's ``transition_recommendation`` in the
orchestrator and enforced at the repo so an SQL-level update can't
sneak past it.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repopulse.db.models.recommendation import RecommendationORM
from repopulse.db.models.recommendation_transition import (
    RecommendationTransitionORM,
)
from repopulse.db.repository.base import utc_now
from repopulse.recommend.engine import Recommendation, State

ToState = Literal["approved", "rejected"]


def _to_recommendation_domain(orm: RecommendationORM) -> Recommendation:
    return Recommendation(
        recommendation_id=orm.recommendation_id,
        incident_id=orm.incident_id,
        action_category=orm.action_category,  # type: ignore[arg-type]
        confidence=orm.confidence,
        risk_level=orm.risk_level,  # type: ignore[arg-type]
        evidence_trace=tuple(orm.evidence_trace),
        state=orm.state,  # type: ignore[arg-type]
    )


class RecommendationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(self, rec: Recommendation) -> None:
        self._session.add(
            RecommendationORM(
                recommendation_id=rec.recommendation_id,
                incident_id=rec.incident_id,
                action_category=rec.action_category,
                confidence=rec.confidence,
                risk_level=rec.risk_level,
                evidence_trace=list(rec.evidence_trace),
                state=rec.state,
            )
        )

    async def count(self) -> int:
        from sqlalchemy import func

        result = await self._session.execute(
            select(func.count()).select_from(RecommendationORM)
        )
        return int(result.scalar_one())

    async def list_latest(self, limit: int = 10) -> list[Recommendation]:
        if limit < 0:
            raise ValueError(f"limit must be >= 0, got {limit!r}")
        # No created_at column — we order by the linked incident's
        # ended_at so "latest" matches v1.1's evaluate-time appendleft.
        from repopulse.db.models.incident import IncidentORM

        stmt = (
            select(RecommendationORM)
            .join(
                IncidentORM,
                RecommendationORM.incident_id == IncidentORM.incident_id,
            )
            .order_by(IncidentORM.ended_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [_to_recommendation_domain(r) for r in result.scalars()]

    async def find_by_id(self, rec_id: UUID) -> Recommendation | None:
        orm = await self._session.get(RecommendationORM, rec_id)
        return _to_recommendation_domain(orm) if orm is not None else None

    async def update_state(
        self,
        rec_id: UUID,
        *,
        to_state: ToState,
        actor: str,
        reason: str | None = None,
        at: datetime | None = None,
    ) -> Recommendation:
        """Transition a pending recommendation. Atomic with the transition row.

        Raises:
            KeyError: recommendation does not exist.
            ValueError: current state is not ``pending``.
        """
        orm = await self._session.get(RecommendationORM, rec_id)
        if orm is None:
            raise KeyError(rec_id)
        from_state: State = orm.state  # type: ignore[assignment]
        if from_state != "pending":
            raise ValueError(
                f"cannot transition state {from_state!r} → {to_state!r}; "
                "only pending → approved|rejected is allowed"
            )
        orm.state = to_state
        self._session.add(
            RecommendationTransitionORM(
                recommendation_id=rec_id,
                from_state=from_state,
                to_state=to_state,
                actor=actor,
                reason=reason,
                at=at if at is not None else utc_now(),
            )
        )
        return _to_recommendation_domain(orm)


__all__ = ["RecommendationRepository", "ToState"]

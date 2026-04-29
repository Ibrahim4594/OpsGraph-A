"""Action-history repository — operator + system audit feed.

Append-only. The only writes:
- ``approve`` / ``reject``: from operator UI flow, paired with a
  ``RecommendationRepository.update_state`` call in the same transaction.
- ``observe``: from the orchestrator when R1 fallback fires.
- ``workflow-run``: from the M5 ``/api/v1/github/usage`` ingest path.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repopulse.db.models.action_history import ActionHistoryORM
from repopulse.pipeline.orchestrator import ActionHistoryEntry

ActionKind = Literal["approve", "reject", "observe", "workflow-run"]


def _to_history_domain(orm: ActionHistoryORM) -> ActionHistoryEntry:
    return ActionHistoryEntry(
        at=orm.at,
        kind=orm.kind,  # type: ignore[arg-type]
        recommendation_id=orm.recommendation_id,
        actor=orm.actor,
        summary=orm.summary,
    )


class ActionHistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        *,
        at: datetime,
        kind: ActionKind,
        recommendation_id: UUID | None,
        actor: str,
        summary: str = "",
    ) -> None:
        self._session.add(
            ActionHistoryORM(
                at=at,
                kind=kind,
                recommendation_id=recommendation_id,
                actor=actor,
                summary=summary,
            )
        )

    async def list_latest(self, limit: int = 50) -> list[ActionHistoryEntry]:
        if limit < 0:
            raise ValueError(f"limit must be >= 0, got {limit!r}")
        stmt = (
            select(ActionHistoryORM)
            .order_by(ActionHistoryORM.at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [_to_history_domain(r) for r in result.scalars()]


__all__ = ["ActionHistoryRepository", "ActionKind"]

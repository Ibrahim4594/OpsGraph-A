"""Workflow-usage repository — agentic GitHub run telemetry.

Idempotent on ``(run_id, repository)`` — GitHub guarantees ``run_id`` is
unique within a repository, so re-POSTs of the same usage payload (e.g.
network retry) collapse into a single row via
``ON CONFLICT (run_id, repository) DO NOTHING RETURNING id``.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from repopulse.db.models.workflow_usage import WorkflowUsageORM
from repopulse.github.usage import WorkflowUsage


def _to_workflow_domain(orm: WorkflowUsageORM) -> WorkflowUsage:
    return WorkflowUsage(
        workflow_name=orm.workflow_name,
        run_id=orm.run_id,
        duration_seconds=orm.duration_seconds,
        conclusion=orm.conclusion,
        repository=orm.repository,
        cost_estimate_usd=orm.cost_estimate_usd,
    )


class WorkflowUsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_idempotent(
        self,
        usage: WorkflowUsage,
        *,
        received_at: datetime,
    ) -> bool:
        """Persist a workflow run; return ``True`` iff a new row landed.

        On conflict the existing row is preserved unchanged — re-POSTing a
        run never overwrites the original ``cost_estimate_usd`` (which is
        derived from a static rate table that may have shifted between
        ingests).
        """
        stmt = (
            pg_insert(WorkflowUsageORM)
            .values(
                workflow_name=usage.workflow_name,
                run_id=usage.run_id,
                duration_seconds=usage.duration_seconds,
                conclusion=usage.conclusion,
                repository=usage.repository,
                cost_estimate_usd=usage.cost_estimate_usd,
                received_at=received_at,
            )
            .on_conflict_do_nothing(
                index_elements=["run_id", "repository"]
            )
            .returning(WorkflowUsageORM.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def list_latest(self, limit: int = 50) -> list[WorkflowUsage]:
        if limit < 0:
            raise ValueError(f"limit must be >= 0, got {limit!r}")
        stmt = (
            select(WorkflowUsageORM)
            .order_by(WorkflowUsageORM.received_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [_to_workflow_domain(r) for r in result.scalars()]


__all__ = ["WorkflowUsageRepository"]

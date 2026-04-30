"""Integration tests — ActionHistoryRepository + WorkflowUsageRepository.

Covers:

- ActionHistory: append + list_latest (newest-first), nullable
  ``recommendation_id`` for ``workflow-run`` rows, kind CHECK
  constraint enforces the documented set.
- WorkflowUsage: ``upsert_idempotent`` returns True on first insert,
  False on duplicate ``(run_id, repository)`` (the natural key GitHub
  guarantees per repository). Duplicate insert leaves only one row;
  the original ``cost_estimate_usd`` is preserved.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repopulse.db.models.action_history import ActionHistoryORM
from repopulse.db.models.workflow_usage import WorkflowUsageORM
from repopulse.db.repository.action_history_repo import ActionHistoryRepository
from repopulse.db.repository.workflow_usage_repo import WorkflowUsageRepository
from repopulse.github.usage import WorkflowUsage

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# action_history
# ---------------------------------------------------------------------------


async def test_action_history_append_and_list_latest_newest_first(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    base = datetime(2026, 4, 29, 10, tzinfo=UTC)
    rec_id = uuid4()
    async with session_maker.begin() as session:
        repo = ActionHistoryRepository(session)
        await repo.append(
            at=base.replace(hour=10),
            kind="approve",
            recommendation_id=rec_id,
            actor="ibrahim",
            summary="approving R3",
        )
        await repo.append(
            at=base.replace(hour=12),
            kind="observe",
            recommendation_id=rec_id,
            actor="system",
            summary="R1 fallback",
        )

    async with session_maker.begin() as session:
        rows = await ActionHistoryRepository(session).list_latest(limit=10)

    assert [r.kind for r in rows] == ["observe", "approve"]
    assert rows[0].actor == "system"
    assert rows[1].actor == "ibrahim"


async def test_action_history_nullable_recommendation_id_for_workflow_run(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """``workflow-run`` rows do NOT carry a recommendation_id."""
    async with session_maker.begin() as session:
        await ActionHistoryRepository(session).append(
            at=datetime(2026, 4, 29, 12, tzinfo=UTC),
            kind="workflow-run",
            recommendation_id=None,
            actor="ci.yml",
            summary="run 1234: success",
        )

    async with session_maker.begin() as session:
        rows = await ActionHistoryRepository(session).list_latest()

    assert len(rows) == 1
    assert rows[0].recommendation_id is None
    assert rows[0].kind == "workflow-run"


async def test_action_history_kind_check_rejects_invalid_value(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """The CHECK constraint guards against silent typos in kind values."""
    with pytest.raises(IntegrityError):
        async with session_maker.begin() as session:
            session.add(
                ActionHistoryORM(
                    at=datetime(2026, 4, 29, 12, tzinfo=UTC),
                    kind="not-a-kind",
                    recommendation_id=None,
                    actor="x",
                    summary="",
                )
            )


# ---------------------------------------------------------------------------
# workflow_usage: idempotent on (run_id, repository)
# ---------------------------------------------------------------------------


def _usage(*, run_id: int = 12345, repository: str = "owner/repo") -> WorkflowUsage:
    return WorkflowUsage(
        workflow_name="ci",
        run_id=run_id,
        duration_seconds=120.0,
        conclusion="success",
        repository=repository,
        cost_estimate_usd=0.016,
    )


async def test_workflow_usage_upsert_returns_true_on_first_insert(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with session_maker.begin() as session:
        ok = await WorkflowUsageRepository(session).upsert_idempotent(
            _usage(),
            received_at=datetime(2026, 4, 29, 12, tzinfo=UTC),
        )
    assert ok is True


async def test_workflow_usage_upsert_returns_false_on_duplicate_key(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Re-POSTing a run with the same ``(run_id, repository)`` collides
    with the UNIQUE constraint via ON CONFLICT — second call returns
    False, only one row in the table.
    """
    async with session_maker.begin() as session:
        first = await WorkflowUsageRepository(session).upsert_idempotent(
            _usage(),
            received_at=datetime(2026, 4, 29, 12, tzinfo=UTC),
        )

    async with session_maker.begin() as session:
        second = await WorkflowUsageRepository(session).upsert_idempotent(
            _usage(),  # same run_id + repository
            received_at=datetime(2026, 4, 29, 12, 5, tzinfo=UTC),
        )

    assert first is True
    assert second is False

    async with session_maker.begin() as session:
        n = await session.execute(
            select(func.count()).select_from(WorkflowUsageORM)
        )
    assert n.scalar_one() == 1


async def test_workflow_usage_upsert_preserves_original_cost(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """ON CONFLICT DO NOTHING: the original ``cost_estimate_usd`` is
    preserved on a duplicate POST — even if the second envelope carries
    a different (later) rate-table value.
    """
    original = _usage()
    later = WorkflowUsage(
        workflow_name=original.workflow_name,
        run_id=original.run_id,
        duration_seconds=original.duration_seconds,
        conclusion=original.conclusion,
        repository=original.repository,
        cost_estimate_usd=999.99,  # bogus to make the test obvious
    )

    async with session_maker.begin() as session:
        await WorkflowUsageRepository(session).upsert_idempotent(
            original, received_at=datetime(2026, 4, 29, 12, tzinfo=UTC)
        )
    async with session_maker.begin() as session:
        await WorkflowUsageRepository(session).upsert_idempotent(
            later, received_at=datetime(2026, 4, 29, 12, 5, tzinfo=UTC)
        )

    async with session_maker.begin() as session:
        cost = await session.execute(
            text("SELECT cost_estimate_usd FROM workflow_usage")
        )
    assert cost.scalar_one() == pytest.approx(0.016)


async def test_workflow_usage_distinct_repos_with_same_run_id_both_persist(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """The UNIQUE is on ``(run_id, repository)`` — same run_id under a
    different repo is NOT a conflict. (GitHub run_ids are unique only
    within a repo.)"""
    async with session_maker.begin() as session:
        a = await WorkflowUsageRepository(session).upsert_idempotent(
            _usage(run_id=42, repository="owner/repo-a"),
            received_at=datetime(2026, 4, 29, 12, tzinfo=UTC),
        )
    async with session_maker.begin() as session:
        b = await WorkflowUsageRepository(session).upsert_idempotent(
            _usage(run_id=42, repository="owner/repo-b"),
            received_at=datetime(2026, 4, 29, 12, tzinfo=UTC),
        )
    assert a is True
    assert b is True

    async with session_maker.begin() as session:
        n = await session.execute(
            select(func.count()).select_from(WorkflowUsageORM)
        )
    assert n.scalar_one() == 2

"""Integration tests — RecommendationRepository (transactional approve/reject).

Covers:

- ``insert`` + ``find_by_id`` + ``list_latest`` round-trip with the
  Postgres-side JSONB encoding of ``evidence_trace``.
- ``update_state`` succeeds for ``pending`` rows: the recommendation's
  state changes AND a row lands in ``recommendation_transitions``,
  both committed in the same transaction.
- ``update_state`` is **atomic on rollback**: when the surrounding
  transaction is rolled back, NEITHER the state change NOR the
  transition row persists.
- ``update_state`` rejects non-``pending`` states with ``ValueError``;
  no transition row is written.
- ``update_state`` raises ``KeyError`` for unknown rec_ids; no rows
  are written.
- ``list_latest`` orders by the linked incident's ``ended_at`` (the
  v1.1 evaluate-time appendleft ordering, lifted into a JOIN).
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repopulse.correlation.engine import Incident
from repopulse.db.models.recommendation_transition import (
    RecommendationTransitionORM,
)
from repopulse.db.repository.incident_repo import IncidentRepository
from repopulse.db.repository.recommendation_repo import RecommendationRepository
from repopulse.pipeline.types import compute_signature_hash
from repopulse.recommend.engine import Recommendation

pytestmark = pytest.mark.integration


def _incident(*, ended_at: datetime) -> Incident:
    return Incident(
        incident_id=uuid4(),
        started_at=ended_at.replace(minute=0),
        ended_at=ended_at,
        sources=("github",),
        anomalies=(),
        events=(),
    )


def _recommendation(
    incident_id: UUID,
    *,
    state: str = "pending",
    action: str = "escalate",
) -> Recommendation:
    return Recommendation(
        recommendation_id=uuid4(),
        incident_id=incident_id,
        action_category=action,  # type: ignore[arg-type]
        confidence=0.85,
        risk_level="medium",
        evidence_trace=("R3: ≥2 anomalies → escalate",),
        state=state,  # type: ignore[arg-type]
    )


async def _seed_incident(
    session_maker: async_sessionmaker[AsyncSession], *, ended_at: datetime
) -> Incident:
    inc = _incident(ended_at=ended_at)
    async with session_maker.begin() as session:
        await IncidentRepository(session).insert_with_signature(
            inc, signature_hash=compute_signature_hash(inc), anomaly_ids=[]
        )
    return inc


# ---------------------------------------------------------------------------
# insert + find_by_id round-trip
# ---------------------------------------------------------------------------


async def test_insert_and_find_by_id_preserves_jsonb_evidence_trace(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    inc = await _seed_incident(
        session_maker, ended_at=datetime(2026, 4, 29, 12, tzinfo=UTC)
    )
    rec = _recommendation(inc.incident_id)

    async with session_maker.begin() as session:
        await RecommendationRepository(session).insert(rec)

    async with session_maker.begin() as session:
        loaded = await RecommendationRepository(session).find_by_id(
            rec.recommendation_id
        )

    assert loaded is not None
    assert loaded.recommendation_id == rec.recommendation_id
    assert loaded.evidence_trace == ("R3: ≥2 anomalies → escalate",)
    assert loaded.state == "pending"


async def test_find_by_id_returns_none_for_unknown_id(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with session_maker.begin() as session:
        loaded = await RecommendationRepository(session).find_by_id(uuid4())
    assert loaded is None


# ---------------------------------------------------------------------------
# update_state: state change + transition row in one transaction
# ---------------------------------------------------------------------------


async def test_update_state_writes_state_and_transition_in_same_transaction(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    inc = await _seed_incident(
        session_maker, ended_at=datetime(2026, 4, 29, 12, tzinfo=UTC)
    )
    rec = _recommendation(inc.incident_id)

    async with session_maker.begin() as session:
        await RecommendationRepository(session).insert(rec)

    async with session_maker.begin() as session:
        updated = await RecommendationRepository(session).update_state(
            rec.recommendation_id,
            to_state="approved",
            actor="ibrahim",
            reason="all green",
        )

    assert updated.state == "approved"

    async with session_maker.begin() as session:
        # Verify state change persisted.
        loaded = await RecommendationRepository(session).find_by_id(
            rec.recommendation_id
        )
        # Verify exactly one transition row written.
        rows = await session.execute(
            select(RecommendationTransitionORM).where(
                RecommendationTransitionORM.recommendation_id
                == rec.recommendation_id
            )
        )
        transitions = list(rows.scalars())

    assert loaded is not None
    assert loaded.state == "approved"
    assert len(transitions) == 1
    t = transitions[0]
    assert t.from_state == "pending"
    assert t.to_state == "approved"
    assert t.actor == "ibrahim"
    assert t.reason == "all green"


async def test_update_state_rollback_leaves_neither_state_nor_transition(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """If the transaction wrapping update_state is rolled back, neither
    the state change nor the transition row persists. Atomicity is
    delegated to Postgres — but we verify it explicitly because the
    caller (orchestrator) reads back state across separate sessions.
    """
    inc = await _seed_incident(
        session_maker, ended_at=datetime(2026, 4, 29, 12, tzinfo=UTC)
    )
    rec = _recommendation(inc.incident_id)
    async with session_maker.begin() as session:
        await RecommendationRepository(session).insert(rec)

    # Open a session manually so we can rollback explicitly.
    async with session_maker() as session:
        await RecommendationRepository(session).update_state(
            rec.recommendation_id,
            to_state="approved",
            actor="ibrahim",
        )
        await session.rollback()

    # Verify nothing persisted.
    async with session_maker.begin() as session:
        loaded = await RecommendationRepository(session).find_by_id(
            rec.recommendation_id
        )
        n_transitions = await session.execute(
            select(func.count()).select_from(RecommendationTransitionORM)
        )

    assert loaded is not None
    assert loaded.state == "pending"
    assert n_transitions.scalar_one() == 0


async def test_update_state_rejects_non_pending_with_value_error(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    inc = await _seed_incident(
        session_maker, ended_at=datetime(2026, 4, 29, 12, tzinfo=UTC)
    )
    # Insert a recommendation that is already 'observed' (R1 fallback).
    rec = _recommendation(inc.incident_id, state="observed", action="observe")
    async with session_maker.begin() as session:
        await RecommendationRepository(session).insert(rec)

    with pytest.raises(ValueError, match="cannot transition state"):
        async with session_maker.begin() as session:
            await RecommendationRepository(session).update_state(
                rec.recommendation_id,
                to_state="approved",
                actor="ibrahim",
            )

    # No transition row written.
    async with session_maker.begin() as session:
        n = await session.execute(
            select(func.count()).select_from(RecommendationTransitionORM)
        )
    assert n.scalar_one() == 0


async def test_update_state_unknown_id_raises_key_error_no_writes(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(KeyError):
        async with session_maker.begin() as session:
            await RecommendationRepository(session).update_state(
                uuid4(),
                to_state="approved",
                actor="ibrahim",
            )

    async with session_maker.begin() as session:
        n = await session.execute(
            select(func.count()).select_from(RecommendationTransitionORM)
        )
    assert n.scalar_one() == 0


# ---------------------------------------------------------------------------
# list_latest ordering via incidents.ended_at
# ---------------------------------------------------------------------------


async def test_list_latest_orders_by_linked_incident_ended_at(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    base = datetime(2026, 4, 29, 10, tzinfo=UTC)
    incs = [
        await _seed_incident(session_maker, ended_at=base.replace(hour=h))
        for h in (10, 13, 11)
    ]
    recs = [_recommendation(i.incident_id) for i in incs]
    async with session_maker.begin() as session:
        repo = RecommendationRepository(session)
        for r in recs:
            await repo.insert(r)

    async with session_maker.begin() as session:
        latest = await RecommendationRepository(session).list_latest(limit=10)

    assert len(latest) == 3
    # Order: incident at hour 13, then 11, then 10. Map each rec back via
    # its incident_id to assert ordering.
    incident_hours = {i.incident_id: i.ended_at.hour for i in incs}
    assert [incident_hours[r.incident_id] for r in latest] == [13, 11, 10]


async def test_list_latest_respects_limit(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    base = datetime(2026, 4, 29, 10, tzinfo=UTC)
    for h in range(3):
        inc = await _seed_incident(session_maker, ended_at=base.replace(hour=10 + h))
        rec = _recommendation(inc.incident_id)
        async with session_maker.begin() as session:
            await RecommendationRepository(session).insert(rec)

    async with session_maker.begin() as session:
        latest = await RecommendationRepository(session).list_latest(limit=2)

    assert len(latest) == 2

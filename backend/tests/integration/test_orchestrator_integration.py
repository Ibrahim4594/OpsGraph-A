"""Integration test — full PipelineOrchestrator flow against real Postgres.

Exercises the post-T6 production path end-to-end without HTTP:

1. ``ingest`` persists raw_events + normalized_events; duplicate
   ``event_id`` returns ``None`` and writes nothing.
2. ``record_anomalies`` persists rows + returns minted IDs.
3. ``evaluate`` reads back, correlates, persists incidents (+ bridge
   rows), emits recommendations, and appends an ``observe`` action-
   history row when R1 fires.
4. Re-running ``evaluate`` over unchanged state emits ``[]`` — the
   ``signature_hash`` UNIQUE acts as the idempotency gate exactly the
   way v1.1's ``_seen_keys`` LRU did.
5. ``transition_recommendation`` updates state, writes a transition
   row, AND appends an action-history row in ONE transaction.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.db.models.action_history import ActionHistoryORM
from repopulse.db.models.incident import IncidentORM
from repopulse.db.models.normalized_event import NormalizedEventORM
from repopulse.db.models.raw_event import RawEventORM
from repopulse.db.models.recommendation import RecommendationORM
from repopulse.db.models.recommendation_transition import (
    RecommendationTransitionORM,
)
from repopulse.pipeline.async_orchestrator import PipelineOrchestrator

pytestmark = pytest.mark.integration


_T0 = datetime(2026, 4, 29, 10, tzinfo=UTC)


def _envelope() -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        source="github",
        kind="push",
        payload={"ref": "refs/heads/main"},
    )


def _anomaly(*, ts: datetime, value: float, series: str = "latency_p99",
             severity: str = "warning") -> Anomaly:
    return Anomaly(
        timestamp=ts,
        value=value,
        baseline_median=10.0,
        baseline_mad=2.0,
        score=4.7,
        severity=severity,  # type: ignore[arg-type]
        series_name=series,
    )


def _orch(session_maker: async_sessionmaker[AsyncSession]) -> PipelineOrchestrator:
    return PipelineOrchestrator(session_maker=session_maker)


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------


async def test_orchestrator_ingest_persists_raw_and_normalized(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    orch = _orch(session_maker)
    env = _envelope()
    result = await orch.ingest(env, received_at=_T0)
    assert result is not None
    assert result.event_id == env.event_id

    async with session_maker.begin() as session:
        n_raw = await session.execute(
            select(func.count()).select_from(RawEventORM)
        )
        n_norm = await session.execute(
            select(func.count()).select_from(NormalizedEventORM)
        )
    assert n_raw.scalar_one() == 1
    assert n_norm.scalar_one() == 1


async def test_orchestrator_ingest_duplicate_event_id_returns_none(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Re-ingesting the same envelope is a no-op — only one row in
    ``raw_events`` and ``normalized_events``.
    """
    orch = _orch(session_maker)
    env = _envelope()
    first = await orch.ingest(env, received_at=_T0)
    second = await orch.ingest(env, received_at=_T0)

    assert first is not None
    assert second is None

    async with session_maker.begin() as session:
        n_raw = await session.execute(
            select(func.count()).select_from(RawEventORM)
        )
        n_norm = await session.execute(
            select(func.count()).select_from(NormalizedEventORM)
        )
    assert n_raw.scalar_one() == 1
    assert n_norm.scalar_one() == 1


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------


async def test_orchestrator_evaluate_emits_recommendation_per_new_incident(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    orch = _orch(session_maker)
    # Two anomalies at slightly different timestamps → R3 escalates.
    await orch.record_anomalies(
        [
            _anomaly(ts=_T0, value=42.0, series="latency_p99"),
            _anomaly(ts=_T0 + timedelta(seconds=1), value=43.0, series="latency_p95"),
        ]
    )

    new_recs = await orch.evaluate(window_seconds=300.0)

    assert len(new_recs) == 1
    rec = new_recs[0]
    assert rec.action_category == "escalate"
    assert rec.state == "pending"

    async with session_maker.begin() as session:
        n_inc = await session.execute(
            select(func.count()).select_from(IncidentORM)
        )
        n_rec = await session.execute(
            select(func.count()).select_from(RecommendationORM)
        )
    assert n_inc.scalar_one() == 1
    assert n_rec.scalar_one() == 1


async def test_orchestrator_evaluate_idempotent_on_unchanged_state(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Re-evaluating with no new input emits zero recs — the
    ``signature_hash`` UNIQUE on incidents acts as the gate.
    """
    orch = _orch(session_maker)
    await orch.record_anomalies(
        [_anomaly(ts=_T0, value=42.0)]
    )

    first = await orch.evaluate()
    second = await orch.evaluate()

    assert len(first) == 1
    assert second == []

    async with session_maker.begin() as session:
        n_inc = await session.execute(
            select(func.count()).select_from(IncidentORM)
        )
        n_rec = await session.execute(
            select(func.count()).select_from(RecommendationORM)
        )
    assert n_inc.scalar_one() == 1
    assert n_rec.scalar_one() == 1


async def test_orchestrator_evaluate_appends_observe_for_r1_fallback(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    orch = _orch(session_maker)
    # A lone normalized event with no anomalies → R1 fallback fires →
    # action_history gets an ``observe`` row.
    await orch.ingest(_envelope(), received_at=_T0)
    new_recs = await orch.evaluate()

    assert len(new_recs) == 1
    assert new_recs[0].action_category == "observe"
    assert new_recs[0].state == "observed"

    async with session_maker.begin() as session:
        rows = await session.execute(select(ActionHistoryORM))
        observes = [r for r in rows.scalars() if r.kind == "observe"]
    assert len(observes) == 1
    assert observes[0].actor == "system"
    assert observes[0].recommendation_id == new_recs[0].recommendation_id


# ---------------------------------------------------------------------------
# transition_recommendation: single-tx atomicity
# ---------------------------------------------------------------------------


async def test_orchestrator_transition_writes_state_transition_and_history_in_one_tx(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Approve flow lands UPDATE recommendations.state +
    INSERT recommendation_transitions + INSERT action_history in a
    single transaction. We assert all three rows exist after the call.
    """
    orch = _orch(session_maker)
    # Seed one pending recommendation.
    await orch.record_anomalies(
        [
            _anomaly(ts=_T0, value=42.0, series="latency_p99"),
            _anomaly(ts=_T0 + timedelta(seconds=1), value=43.0, series="latency_p95"),
        ]
    )
    new_recs = await orch.evaluate()
    assert len(new_recs) == 1
    rec_id = new_recs[0].recommendation_id

    updated = await orch.transition_recommendation(
        rec_id, to_state="approved", actor="ibrahim", reason="all green"
    )

    assert updated.state == "approved"

    async with session_maker.begin() as session:
        # state column updated
        rec_row = await session.execute(
            select(RecommendationORM).where(
                RecommendationORM.recommendation_id == rec_id
            )
        )
        rec_orm = rec_row.scalar_one()
        # exactly one transition row
        trans_rows = await session.execute(
            select(RecommendationTransitionORM).where(
                RecommendationTransitionORM.recommendation_id == rec_id
            )
        )
        transitions = list(trans_rows.scalars())
        # exactly one approve action_history row for this rec
        hist_rows = await session.execute(
            select(ActionHistoryORM).where(
                ActionHistoryORM.recommendation_id == rec_id,
                ActionHistoryORM.kind == "approve",
            )
        )
        approves = list(hist_rows.scalars())

    assert rec_orm.state == "approved"
    assert len(transitions) == 1
    assert transitions[0].from_state == "pending"
    assert transitions[0].to_state == "approved"
    assert transitions[0].actor == "ibrahim"
    assert transitions[0].reason == "all green"
    assert len(approves) == 1
    assert approves[0].actor == "ibrahim"


async def test_orchestrator_transition_propagates_value_error_no_partial_writes(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """When transition_recommendation raises (non-pending state), the
    transaction is rolled back — neither the recommendations.state
    column nor a new transition / history row is mutated.
    """
    orch = _orch(session_maker)
    # Seed an R1 recommendation (state=observed; non-pending → invalid).
    await orch.ingest(_envelope(), received_at=_T0)
    new_recs = await orch.evaluate()
    rec_id = new_recs[0].recommendation_id
    assert new_recs[0].state == "observed"

    # Snapshot pre-state.
    async with session_maker.begin() as session:
        n_history_before = await session.execute(
            select(func.count()).select_from(ActionHistoryORM)
        )
        n_transitions_before = await session.execute(
            select(func.count()).select_from(RecommendationTransitionORM)
        )

    with pytest.raises(ValueError, match="cannot transition state"):
        await orch.transition_recommendation(
            rec_id, to_state="approved", actor="ibrahim"
        )

    async with session_maker.begin() as session:
        n_history_after = await session.execute(
            select(func.count()).select_from(ActionHistoryORM)
        )
        n_transitions_after = await session.execute(
            select(func.count()).select_from(RecommendationTransitionORM)
        )
        rec_after = await session.execute(
            select(RecommendationORM).where(
                RecommendationORM.recommendation_id == rec_id
            )
        )

    # No partial writes after failure.
    assert n_history_after.scalar_one() == n_history_before.scalar_one()
    assert n_transitions_after.scalar_one() == n_transitions_before.scalar_one()
    assert rec_after.scalar_one().state == "observed"


# ---------------------------------------------------------------------------
# snapshot — counts roll up correctly through the repo path
# ---------------------------------------------------------------------------


async def test_orchestrator_snapshot_reports_aggregate_counts(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    orch = _orch(session_maker)
    # 2 events, 1 anomaly → 1 incident, 1 recommendation after evaluate.
    await orch.ingest(_envelope(), received_at=_T0)
    await orch.ingest(_envelope(), received_at=_T0 + timedelta(seconds=10))
    await orch.record_anomalies([_anomaly(ts=_T0, value=42.0)])
    await orch.evaluate()

    snap = await orch.snapshot()
    assert snap == {
        "events": 2,
        "anomalies": 1,
        "incidents": 1,
        "recommendations": 1,
    }

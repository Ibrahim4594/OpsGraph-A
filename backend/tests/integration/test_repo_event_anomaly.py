"""Integration tests — EventRepository + AnomalyRepository round-trips.

Covers:

- ``insert_raw_idempotent`` returns True on first insert, False on
  duplicate ``event_id`` (the v1.1 ``_seen_keys`` per-event side, lifted
  into the database via ``ON CONFLICT (event_id) DO NOTHING RETURNING``).
- Duplicate insert leaves only one row in ``raw_events``.
- ``insert_normalized`` persists the 1:1 row keyed off ``event_id``.
- ``list_recent_normalized`` returns oldest-first (matches the
  legacy in-memory deque semantics that ``correlate()`` expects).
- ``count_normalized`` reflects actual row count.
- ``insert_many`` mints UUIDs and persists every anomaly; returned IDs
  match the rows.
- ``list_recent_with_ids`` returns ``(id, Anomaly)`` pairs ordered by
  timestamp ascending.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.db.repository.anomaly_repo import AnomalyRepository
from repopulse.db.repository.event_repo import EventRepository
from repopulse.pipeline.normalize import NormalizedEvent

pytestmark = pytest.mark.integration


def _envelope(event_id: UUID | None = None) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id or uuid4(),
        source="github",
        kind="push",
        payload={"ref": "refs/heads/main"},
    )


def _normalized(event_id: UUID, *, ts: datetime) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id,
        received_at=ts,
        occurred_at=ts,
        source="github",
        kind="ci-failure",
        severity="error",
        attributes={"workflow": "ci"},
    )


def _anomaly(*, ts: datetime, value: float, series: str = "latency_p99") -> Anomaly:
    return Anomaly(
        timestamp=ts,
        value=value,
        baseline_median=10.0,
        baseline_mad=2.0,
        score=4.7,
        severity="warning",
        series_name=series,
    )


# ---------------------------------------------------------------------------
# raw_events: ON CONFLICT DO NOTHING / RETURNING
# ---------------------------------------------------------------------------


async def test_insert_raw_idempotent_returns_true_on_fresh_event_id(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    env = _envelope()
    ts = datetime(2026, 4, 29, 12, tzinfo=UTC)

    async with session_maker.begin() as session:
        repo = EventRepository(session)
        result = await repo.insert_raw_idempotent(
            env, received_at=ts, occurred_at=ts
        )

    assert result is True


async def test_insert_raw_idempotent_returns_false_on_duplicate_event_id(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Duplicate POST returns False; only one row in raw_events."""
    env = _envelope()
    ts = datetime(2026, 4, 29, 12, tzinfo=UTC)

    async with session_maker.begin() as session:
        first = await EventRepository(session).insert_raw_idempotent(
            env, received_at=ts, occurred_at=ts
        )

    async with session_maker.begin() as session:
        second = await EventRepository(session).insert_raw_idempotent(
            env, received_at=ts, occurred_at=ts
        )

    assert first is True
    assert second is False

    # Verify exactly one row.
    from sqlalchemy import func, select

    from repopulse.db.models.raw_event import RawEventORM

    async with session_maker.begin() as session:
        count = await session.execute(
            select(func.count()).select_from(RawEventORM)
        )
        assert int(count.scalar_one()) == 1


# ---------------------------------------------------------------------------
# normalized_events: 1:1 with raw_events, oldest-first list
# ---------------------------------------------------------------------------


async def test_insert_normalized_persists_with_shared_pk_fk(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    env = _envelope()
    ts = datetime(2026, 4, 29, 12, tzinfo=UTC)

    async with session_maker.begin() as session:
        repo = EventRepository(session)
        await repo.insert_raw_idempotent(env, received_at=ts, occurred_at=ts)
        await repo.insert_normalized(_normalized(env.event_id, ts=ts))

    async with session_maker.begin() as session:
        rows = await EventRepository(session).list_recent_normalized()

    assert len(rows) == 1
    assert rows[0].event_id == env.event_id
    assert rows[0].source == "github"
    assert rows[0].severity == "error"
    assert rows[0].attributes == {"workflow": "ci"}


async def test_list_recent_normalized_returns_oldest_first(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """correlate() folds events into a sorted timeline; the repo must
    hand them to it oldest-first.
    """
    base = datetime(2026, 4, 29, 10, tzinfo=UTC)
    envs = [_envelope() for _ in range(3)]
    timestamps = [
        base.replace(hour=10),
        base.replace(hour=11),
        base.replace(hour=12),
    ]

    async with session_maker.begin() as session:
        repo = EventRepository(session)
        for env, ts in zip(envs, timestamps, strict=True):
            await repo.insert_raw_idempotent(env, received_at=ts, occurred_at=ts)
            await repo.insert_normalized(_normalized(env.event_id, ts=ts))

    async with session_maker.begin() as session:
        rows = await EventRepository(session).list_recent_normalized()

    assert [r.received_at for r in rows] == timestamps


async def test_count_normalized_returns_row_count(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    base = datetime(2026, 4, 29, 12, tzinfo=UTC)
    async with session_maker.begin() as session:
        repo = EventRepository(session)
        for i in range(4):
            env = _envelope()
            ts = base.replace(minute=i)
            await repo.insert_raw_idempotent(env, received_at=ts, occurred_at=ts)
            await repo.insert_normalized(_normalized(env.event_id, ts=ts))

    async with session_maker.begin() as session:
        n = await EventRepository(session).count_normalized()

    assert n == 4


# ---------------------------------------------------------------------------
# anomalies: insert_many returns IDs; list_recent_with_ids ordered
# ---------------------------------------------------------------------------


async def test_insert_many_returns_minted_ids_and_persists_every_row(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    base = datetime(2026, 4, 29, 10, tzinfo=UTC)
    items = [_anomaly(ts=base.replace(minute=i), value=10.0 + i) for i in range(3)]

    async with session_maker.begin() as session:
        ids = await AnomalyRepository(session).insert_many(items)

    assert len(ids) == 3
    assert all(isinstance(i, UUID) for i in ids)
    assert len(set(ids)) == 3  # no collisions

    async with session_maker.begin() as session:
        n = await AnomalyRepository(session).count()
    assert n == 3


async def test_list_recent_with_ids_returns_oldest_first(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    base = datetime(2026, 4, 29, 10, tzinfo=UTC)
    items = [_anomaly(ts=base.replace(minute=m), value=10.0) for m in (5, 1, 9)]

    async with session_maker.begin() as session:
        repo = AnomalyRepository(session)
        await repo.insert_many(items)

    async with session_maker.begin() as session:
        pairs = await AnomalyRepository(session).list_recent_with_ids()

    assert [a.timestamp.minute for _, a in pairs] == [1, 5, 9]


async def test_anomaly_severity_check_rejects_invalid_value(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """The CHECK constraint rejects severities outside the documented set."""
    from sqlalchemy.exc import IntegrityError

    from repopulse.db.models.anomaly import AnomalyORM

    base = datetime(2026, 4, 29, 10, tzinfo=UTC)
    with pytest.raises(IntegrityError):
        async with session_maker.begin() as session:
            session.add(
                AnomalyORM(
                    id=uuid4(),
                    timestamp=base,
                    value=42.0,
                    baseline_median=10.0,
                    baseline_mad=2.0,
                    score=5.0,
                    severity="not-a-real-severity",
                    series_name="latency_p99",
                )
            )

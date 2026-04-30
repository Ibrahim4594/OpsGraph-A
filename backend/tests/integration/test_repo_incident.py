"""Integration tests — IncidentRepository.

Covers:

- ``insert_with_signature`` returns True on first insert, False on
  duplicate ``signature_hash`` (the v1.1 ``_seen_keys`` content side,
  lifted into the database via ``ON CONFLICT (signature_hash) DO
  NOTHING RETURNING``).
- Bridge rows (``incident_events``, ``incident_anomalies``) are written
  in the same transaction as the parent incident.
- Deleting an incident CASCADEs through both bridges (rows for that
  incident vanish; the underlying events / anomalies are NOT deleted —
  the bridge FK has CASCADE on delete only on the *bridge* side).
- ``list_recent`` returns shallow shells newest-first by ``ended_at``.
- ``list_recent_with_counts`` returns ``(Incident, anomaly_count,
  event_count)`` triples — the dashboard's incidents-list shape.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.correlation.engine import Incident
from repopulse.db.repository.anomaly_repo import AnomalyRepository
from repopulse.db.repository.event_repo import EventRepository
from repopulse.db.repository.incident_repo import IncidentRepository
from repopulse.pipeline.normalize import NormalizedEvent
from repopulse.pipeline.types import compute_signature_hash

pytestmark = pytest.mark.integration


def _envelope(event_id: UUID | None = None) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id or uuid4(),
        source="github",
        kind="push",
        payload={},
    )


def _normalized(event_id: UUID, *, ts: datetime) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id,
        received_at=ts,
        occurred_at=ts,
        source="github",
        kind="ci-failure",
        severity="error",
        attributes={},
    )


def _anomaly(*, ts: datetime, value: float) -> Anomaly:
    return Anomaly(
        timestamp=ts,
        value=value,
        baseline_median=10.0,
        baseline_mad=2.0,
        score=4.7,
        severity="warning",
        series_name="latency_p99",
    )


def _incident(
    *,
    started_at: datetime,
    ended_at: datetime,
    events: tuple[NormalizedEvent, ...] = (),
    anomalies: tuple[Anomaly, ...] = (),
    sources: tuple[str, ...] = ("github",),
) -> Incident:
    return Incident(
        incident_id=uuid4(),
        started_at=started_at,
        ended_at=ended_at,
        sources=sources,
        anomalies=anomalies,
        events=events,
    )


async def _seed_event(
    session_maker: async_sessionmaker[AsyncSession], *, ts: datetime
) -> NormalizedEvent:
    env = _envelope()
    async with session_maker.begin() as session:
        repo = EventRepository(session)
        await repo.insert_raw_idempotent(env, received_at=ts, occurred_at=ts)
        norm = _normalized(env.event_id, ts=ts)
        await repo.insert_normalized(norm)
    return norm


async def _seed_anomalies(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    items: list[Anomaly],
) -> list[UUID]:
    async with session_maker.begin() as session:
        return await AnomalyRepository(session).insert_many(items)


# ---------------------------------------------------------------------------
# signature_hash UNIQUE / conflict
# ---------------------------------------------------------------------------


async def test_insert_with_signature_returns_true_on_fresh_signature(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    base = datetime(2026, 4, 29, 10, tzinfo=UTC)
    inc = _incident(started_at=base, ended_at=base.replace(minute=5))

    async with session_maker.begin() as session:
        repo = IncidentRepository(session)
        result = await repo.insert_with_signature(
            inc,
            signature_hash=compute_signature_hash(inc),
            anomaly_ids=[],
        )

    assert result is True


async def test_insert_with_signature_returns_false_on_duplicate(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Same signature_hash collides with the UNIQUE constraint — second
    insert returns False, no second row, no bridge rows for the second
    attempt.
    """
    base = datetime(2026, 4, 29, 10, tzinfo=UTC)
    inc1 = _incident(started_at=base, ended_at=base.replace(minute=5))
    sig = compute_signature_hash(inc1)

    async with session_maker.begin() as session:
        first = await IncidentRepository(session).insert_with_signature(
            inc1, signature_hash=sig, anomaly_ids=[]
        )

    # A different incident_id but same signature_hash MUST collide.
    inc2 = _incident(started_at=base, ended_at=base.replace(minute=5))
    async with session_maker.begin() as session:
        second = await IncidentRepository(session).insert_with_signature(
            inc2, signature_hash=sig, anomaly_ids=[]
        )

    assert first is True
    assert second is False

    async with session_maker.begin() as session:
        n = await IncidentRepository(session).count()
    assert n == 1


# ---------------------------------------------------------------------------
# Bridge tables: rows written in same tx; CASCADE on incident delete
# ---------------------------------------------------------------------------


async def test_insert_with_signature_writes_bridge_rows_in_same_transaction(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    base = datetime(2026, 4, 29, 10, tzinfo=UTC)
    norm1 = await _seed_event(session_maker, ts=base.replace(minute=1))
    norm2 = await _seed_event(session_maker, ts=base.replace(minute=2))
    anomaly_ids = await _seed_anomalies(
        session_maker,
        items=[_anomaly(ts=base.replace(minute=3), value=42.0)],
    )

    inc = _incident(
        started_at=base,
        ended_at=base.replace(minute=5),
        events=(norm1, norm2),
    )
    async with session_maker.begin() as session:
        await IncidentRepository(session).insert_with_signature(
            inc,
            signature_hash=compute_signature_hash(inc),
            anomaly_ids=anomaly_ids,
        )

    async with session_maker.begin() as session:
        ev_count = await session.execute(
            text("SELECT COUNT(*) FROM incident_events WHERE incident_id = :id"),
            {"id": inc.incident_id},
        )
        an_count = await session.execute(
            text("SELECT COUNT(*) FROM incident_anomalies WHERE incident_id = :id"),
            {"id": inc.incident_id},
        )
    assert ev_count.scalar_one() == 2
    assert an_count.scalar_one() == 1


async def test_deleting_incident_cascades_to_both_bridge_tables(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """``ON DELETE CASCADE`` on the bridge FKs purges links when an
    incident is deleted; the underlying events + anomalies remain."""
    base = datetime(2026, 4, 29, 10, tzinfo=UTC)
    norm = await _seed_event(session_maker, ts=base.replace(minute=1))
    anomaly_ids = await _seed_anomalies(
        session_maker,
        items=[_anomaly(ts=base.replace(minute=3), value=42.0)],
    )
    inc = _incident(
        started_at=base,
        ended_at=base.replace(minute=5),
        events=(norm,),
    )
    async with session_maker.begin() as session:
        await IncidentRepository(session).insert_with_signature(
            inc,
            signature_hash=compute_signature_hash(inc),
            anomaly_ids=anomaly_ids,
        )

    # Sanity: bridges exist before delete.
    async with session_maker.begin() as session:
        rows = await session.execute(
            text("SELECT COUNT(*) FROM incident_events"),
        )
        assert rows.scalar_one() == 1

    # Delete the incident.
    async with session_maker.begin() as session:
        await session.execute(
            text("DELETE FROM incidents WHERE incident_id = :id"),
            {"id": inc.incident_id},
        )

    async with session_maker.begin() as session:
        ev = await session.execute(text("SELECT COUNT(*) FROM incident_events"))
        an = await session.execute(text("SELECT COUNT(*) FROM incident_anomalies"))
        underlying_ev = await session.execute(
            text("SELECT COUNT(*) FROM normalized_events")
        )
        underlying_an = await session.execute(
            text("SELECT COUNT(*) FROM anomalies")
        )

    assert ev.scalar_one() == 0
    assert an.scalar_one() == 0
    # Underlying rows are NOT cascade-deleted: the bridge FK is the one
    # with CASCADE, not the incident-side FK on the underlying tables.
    assert underlying_ev.scalar_one() == 1
    assert underlying_an.scalar_one() == 1


# ---------------------------------------------------------------------------
# list_recent + list_recent_with_counts
# ---------------------------------------------------------------------------


async def test_list_recent_returns_newest_first_by_ended_at(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    base = datetime(2026, 4, 29, 10, tzinfo=UTC)
    incidents = [
        _incident(started_at=base.replace(hour=h), ended_at=base.replace(hour=h, minute=5))
        for h in (10, 13, 11)
    ]
    async with session_maker.begin() as session:
        repo = IncidentRepository(session)
        for inc in incidents:
            await repo.insert_with_signature(
                inc,
                signature_hash=compute_signature_hash(inc),
                anomaly_ids=[],
            )

    async with session_maker.begin() as session:
        recent = await IncidentRepository(session).list_recent(limit=10)

    assert [inc.ended_at.hour for inc in recent] == [13, 11, 10]


async def test_list_recent_with_counts_returns_bridge_counts(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    base = datetime(2026, 4, 29, 10, tzinfo=UTC)
    norm1 = await _seed_event(session_maker, ts=base.replace(minute=1))
    norm2 = await _seed_event(session_maker, ts=base.replace(minute=2))
    anomaly_ids = await _seed_anomalies(
        session_maker,
        items=[
            _anomaly(ts=base.replace(minute=3), value=42.0),
            _anomaly(ts=base.replace(minute=4), value=43.0),
            _anomaly(ts=base.replace(minute=5), value=44.0),
        ],
    )
    inc = _incident(
        started_at=base,
        ended_at=base.replace(minute=10),
        events=(norm1, norm2),
    )
    async with session_maker.begin() as session:
        await IncidentRepository(session).insert_with_signature(
            inc,
            signature_hash=compute_signature_hash(inc),
            anomaly_ids=anomaly_ids,
        )

    async with session_maker.begin() as session:
        triples = await IncidentRepository(session).list_recent_with_counts()

    assert len(triples) == 1
    incident, anomaly_count, event_count = triples[0]
    assert incident.incident_id == inc.incident_id
    assert anomaly_count == 3
    assert event_count == 2

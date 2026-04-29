"""Unit tests for the async :class:`PipelineOrchestrator` (M2.0 task 5).

Strict scope: orchestration flow + transaction boundaries. No real DB,
no Postgres, no SQLAlchemy session — fakes that record calls. Behavioral
DB roundtrips ship in T10 (Testcontainers).

Coverage:

- ``ingest`` returns the normalized event on a fresh ``event_id`` and
  ``None`` (idempotent skip) on a duplicate.
- ``record_anomalies`` returns minted IDs and writes through one
  transaction.
- ``evaluate`` correlates over current state, dedupes by signature_hash,
  emits one recommendation per fresh incident, and appends an
  ``observe`` action-history row when the R1 fallback fires.
- ``transition_recommendation`` performs ``update_state`` then ``append``
  in the SAME session / transaction (the documented "single tx" carve-out).
- ``transition_recommendation`` propagates the repo's
  ``ValueError`` / ``KeyError`` rather than swallowing them.
"""
from __future__ import annotations

from collections.abc import Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.correlation.engine import Incident
from repopulse.pipeline.async_orchestrator import PipelineOrchestrator
from repopulse.pipeline.normalize import NormalizedEvent
from repopulse.pipeline.types import compute_signature_hash
from repopulse.recommend.engine import Recommendation

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeSession:
    """Sentinel — the orchestrator never inspects this object directly."""


class FakeSessionMaker:
    """Mimics ``async_sessionmaker.begin()`` via an async context manager.

    Records how many times ``begin()`` was entered so tests can assert
    that one logical operation == one transaction (the T5 guardrail).
    """

    def __init__(self) -> None:
        self.begin_count = 0

    def begin(self) -> Any:
        self.begin_count += 1

        @asynccontextmanager
        async def _ctx() -> Any:
            yield FakeSession()

        return _ctx()


@dataclass
class FakeEventRepo:
    inserted_raw: list[EventEnvelope] = field(default_factory=list)
    inserted_normalized: list[NormalizedEvent] = field(default_factory=list)
    duplicate_ids: set[UUID] = field(default_factory=set)
    recent_normalized: list[NormalizedEvent] = field(default_factory=list)

    async def insert_raw_idempotent(
        self,
        envelope: EventEnvelope,
        *,
        received_at: datetime,
        occurred_at: datetime,
    ) -> bool:
        if envelope.event_id in self.duplicate_ids:
            return False
        self.inserted_raw.append(envelope)
        return True

    async def insert_normalized(self, event: NormalizedEvent) -> None:
        self.inserted_normalized.append(event)

    async def list_recent_normalized(
        self, *, limit: int = 1000
    ) -> list[NormalizedEvent]:
        return list(self.recent_normalized)


@dataclass
class FakeAnomalyRepo:
    inserted: list[Anomaly] = field(default_factory=list)
    minted_ids: list[UUID] = field(default_factory=list)
    recent_with_ids: list[tuple[UUID, Anomaly]] = field(default_factory=list)

    async def insert_many(self, anomalies: Sequence[Anomaly]) -> list[UUID]:
        new_ids = [uuid4() for _ in anomalies]
        self.inserted.extend(anomalies)
        self.minted_ids.extend(new_ids)
        return new_ids

    async def list_recent_with_ids(
        self, *, limit: int = 200
    ) -> list[tuple[UUID, Anomaly]]:
        return list(self.recent_with_ids)


@dataclass
class FakeIncidentRepo:
    inserts: list[tuple[Incident, str, list[UUID]]] = field(default_factory=list)
    seen_signatures: set[str] = field(default_factory=set)

    async def insert_with_signature(
        self,
        incident: Incident,
        *,
        signature_hash: str,
        anomaly_ids: Sequence[UUID],
    ) -> bool:
        if signature_hash in self.seen_signatures:
            return False
        self.seen_signatures.add(signature_hash)
        self.inserts.append((incident, signature_hash, list(anomaly_ids)))
        return True

    async def list_recent(self, *, limit: int = 100) -> list[Incident]:
        return [inc for inc, _, _ in self.inserts][-limit:][::-1]


@dataclass
class FakeRecommendationRepo:
    inserts: list[Recommendation] = field(default_factory=list)
    transitions: list[tuple[UUID, str, str, str | None]] = field(
        default_factory=list
    )
    by_id: dict[UUID, Recommendation] = field(default_factory=dict)
    next_update_state_raises: BaseException | None = None

    async def insert(self, rec: Recommendation) -> None:
        self.inserts.append(rec)
        self.by_id[rec.recommendation_id] = rec

    async def list_latest(self, limit: int = 10) -> list[Recommendation]:
        return list(self.inserts)[-limit:][::-1]

    async def find_by_id(self, rec_id: UUID) -> Recommendation | None:
        return self.by_id.get(rec_id)

    async def update_state(
        self,
        rec_id: UUID,
        *,
        to_state: str,
        actor: str,
        reason: str | None = None,
        at: datetime | None = None,
    ) -> Recommendation:
        if self.next_update_state_raises is not None:
            raise self.next_update_state_raises
        existing = self.by_id[rec_id]
        # Mirror the real repo: build a new dataclass with state replaced.
        from dataclasses import replace

        updated = replace(existing, state=to_state)  # type: ignore[arg-type]
        self.by_id[rec_id] = updated
        self.transitions.append((rec_id, to_state, actor, reason))
        return updated


@dataclass
class FakeActionHistoryRepo:
    appended: list[dict[str, Any]] = field(default_factory=list)

    async def append(
        self,
        *,
        at: datetime,
        kind: str,
        recommendation_id: UUID | None,
        actor: str,
        summary: str = "",
    ) -> None:
        self.appended.append(
            {
                "at": at,
                "kind": kind,
                "recommendation_id": recommendation_id,
                "actor": actor,
                "summary": summary,
            }
        )

    async def list_latest(self, limit: int = 50) -> list[Any]:
        return list(self.appended)[-limit:][::-1]


@dataclass
class _Fakes:
    """Shared bundle so tests can share one set of fakes across one orch."""

    session_maker: FakeSessionMaker
    events: FakeEventRepo
    anomalies: FakeAnomalyRepo
    incidents: FakeIncidentRepo
    recs: FakeRecommendationRepo
    history: FakeActionHistoryRepo


def _build(clock_at: datetime | None = None) -> tuple[PipelineOrchestrator, _Fakes]:
    session_maker = FakeSessionMaker()
    events = FakeEventRepo()
    anomalies = FakeAnomalyRepo()
    incidents = FakeIncidentRepo()
    recs = FakeRecommendationRepo()
    history = FakeActionHistoryRepo()

    def _clock() -> datetime:
        return clock_at if clock_at is not None else datetime(2026, 4, 29, 12, tzinfo=UTC)

    orch = PipelineOrchestrator(
        session_maker=session_maker,  # type: ignore[arg-type]
        event_repo_factory=lambda _s: events,  # type: ignore[arg-type, return-value]
        anomaly_repo_factory=lambda _s: anomalies,  # type: ignore[arg-type, return-value]
        incident_repo_factory=lambda _s: incidents,  # type: ignore[arg-type, return-value]
        recommendation_repo_factory=lambda _s: recs,  # type: ignore[arg-type, return-value]
        action_history_repo_factory=lambda _s: history,  # type: ignore[arg-type, return-value]
        clock=_clock,
    )
    return orch, _Fakes(
        session_maker=session_maker,
        events=events,
        anomalies=anomalies,
        incidents=incidents,
        recs=recs,
        history=history,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _envelope(*, event_id: UUID | None = None) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id or uuid4(),
        source="github",
        kind="ci-failure",
        payload={"workflow": "ci"},
    )


def _normalized(*, event_id: UUID | None = None, ts: datetime | None = None) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id or uuid4(),
        received_at=ts or datetime(2026, 4, 29, 12, tzinfo=UTC),
        occurred_at=ts or datetime(2026, 4, 29, 12, tzinfo=UTC),
        source="github",
        kind="ci-failure",
        severity="error",
        attributes={},
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


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_persists_raw_and_normalized() -> None:
    orch, f = _build()
    env = _envelope()
    result = await orch.ingest(env)
    assert isinstance(result, NormalizedEvent)
    assert result.event_id == env.event_id
    assert len(f.events.inserted_raw) == 1
    assert len(f.events.inserted_normalized) == 1
    assert f.session_maker.begin_count == 1


@pytest.mark.asyncio
async def test_ingest_duplicate_event_id_returns_none_and_skips_normalize() -> None:
    orch, f = _build()
    env = _envelope()
    f.events.duplicate_ids.add(env.event_id)
    result = await orch.ingest(env)
    assert result is None
    # raw insert ran (and saw the conflict — fake returns False);
    # normalize must NOT have been persisted.
    assert f.events.inserted_normalized == []
    assert f.session_maker.begin_count == 1


# ---------------------------------------------------------------------------
# record_anomalies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_anomalies_returns_minted_ids() -> None:
    orch, f = _build()
    a1 = _anomaly(ts=datetime(2026, 4, 29, 10, tzinfo=UTC), value=42.0)
    a2 = _anomaly(ts=datetime(2026, 4, 29, 10, 1, tzinfo=UTC), value=44.0)
    ids = await orch.record_anomalies([a1, a2])
    assert len(ids) == 2
    assert all(isinstance(i, UUID) for i in ids)
    assert f.anomalies.inserted == [a1, a2]
    assert f.session_maker.begin_count == 1


@pytest.mark.asyncio
async def test_record_anomalies_empty_list_does_not_open_transaction() -> None:
    orch, f = _build()
    ids = await orch.record_anomalies([])
    assert ids == []
    assert f.session_maker.begin_count == 0


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_emits_recommendation_per_new_incident() -> None:
    orch, f = _build()
    # Two anomalies clustered at the same source → R3 escalate (≥2 anomalies).
    aid_1, aid_2 = uuid4(), uuid4()
    t = datetime(2026, 4, 29, 10, tzinfo=UTC)
    a1 = _anomaly(ts=t, value=42.0)
    a2 = _anomaly(ts=t, value=43.0, series="latency_p95")
    f.anomalies.recent_with_ids = [(aid_1, a1), (aid_2, a2)]

    new_recs = await orch.evaluate(window_seconds=300.0)

    assert len(new_recs) == 1
    assert len(f.incidents.inserts) == 1
    incident, sig, anomaly_ids = f.incidents.inserts[0]
    assert sig == compute_signature_hash(incident)
    assert set(anomaly_ids) == {aid_1, aid_2}
    rec = new_recs[0]
    assert rec.action_category == "escalate"  # R3 fired
    assert rec.state == "pending"
    # No observe row for non-R1 outcome.
    assert f.history.appended == []


@pytest.mark.asyncio
async def test_evaluate_idempotent_on_repeat_with_same_state() -> None:
    """Re-running evaluate over unchanged state emits zero new recs."""
    orch, f = _build()
    aid_1 = uuid4()
    a1 = _anomaly(
        ts=datetime(2026, 4, 29, 10, tzinfo=UTC), value=42.0, severity="warning"
    )
    f.anomalies.recent_with_ids = [(aid_1, a1)]

    first = await orch.evaluate()
    second = await orch.evaluate()
    assert len(first) == 1
    assert second == []
    # Only one incident actually got persisted.
    assert len(f.incidents.inserts) == 1


@pytest.mark.asyncio
async def test_evaluate_appends_observe_for_r1_fallback() -> None:
    orch, f = _build()
    # A lone normalized event with no anomalies → R2/R3/R4 don't fire → R1.
    f.events.recent_normalized = [_normalized()]
    new_recs = await orch.evaluate()
    assert len(new_recs) == 1
    assert new_recs[0].action_category == "observe"
    assert new_recs[0].state == "observed"
    # observe row was appended.
    assert len(f.history.appended) == 1
    entry = f.history.appended[0]
    assert entry["kind"] == "observe"
    assert entry["actor"] == "system"
    assert entry["recommendation_id"] == new_recs[0].recommendation_id


# ---------------------------------------------------------------------------
# transition_recommendation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transition_recommendation_runs_update_and_history_in_one_tx() -> None:
    orch, f = _build()
    rec = Recommendation(
        recommendation_id=uuid4(),
        incident_id=uuid4(),
        action_category="escalate",
        confidence=0.85,
        risk_level="medium",
        evidence_trace=("R3",),
        state="pending",
    )
    f.recs.by_id[rec.recommendation_id] = rec

    updated = await orch.transition_recommendation(
        rec.recommendation_id,
        to_state="approved",
        actor="ibrahim",
        reason="all green",
    )

    assert updated.state == "approved"
    assert f.recs.transitions == [
        (rec.recommendation_id, "approved", "ibrahim", "all green")
    ]
    assert len(f.history.appended) == 1
    assert f.history.appended[0]["kind"] == "approve"
    assert f.history.appended[0]["actor"] == "ibrahim"
    assert f.history.appended[0]["recommendation_id"] == rec.recommendation_id
    # Critically: ONE transaction for both writes.
    assert f.session_maker.begin_count == 1


@pytest.mark.asyncio
async def test_transition_recommendation_propagates_value_error() -> None:
    orch, f = _build()
    f.recs.next_update_state_raises = ValueError("not pending")
    with pytest.raises(ValueError, match="not pending"):
        await orch.transition_recommendation(
            uuid4(),
            to_state="approved",
            actor="ibrahim",
        )
    # Critical: history row must NOT be written when the state update fails.
    assert f.history.appended == []


@pytest.mark.asyncio
async def test_transition_recommendation_propagates_key_error() -> None:
    orch, f = _build()
    f.recs.next_update_state_raises = KeyError("missing")
    with pytest.raises(KeyError):
        await orch.transition_recommendation(
            uuid4(),
            to_state="rejected",
            actor="ibrahim",
            reason="duplicate",
        )
    assert f.history.appended == []


# ---------------------------------------------------------------------------
# read paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_recommendation_state_delegates_to_find_by_id() -> None:
    orch, f = _build()
    rec = Recommendation(
        recommendation_id=uuid4(),
        incident_id=uuid4(),
        action_category="triage",
        confidence=0.7,
        risk_level="low",
        evidence_trace=("R2",),
        state="pending",
    )
    f.recs.by_id[rec.recommendation_id] = rec
    state = await orch.get_recommendation_state(rec.recommendation_id)
    assert state == "pending"
    missing = await orch.get_recommendation_state(uuid4())
    assert missing is None


@pytest.mark.asyncio
async def test_negative_limit_raises() -> None:
    orch, _ = _build()
    with pytest.raises(ValueError):
        await orch.latest_recommendations(limit=-1)
    with pytest.raises(ValueError):
        await orch.latest_incidents(limit=-1)
    with pytest.raises(ValueError):
        await orch.latest_actions(limit=-1)

"""In-memory async :class:`PipelineOrchestrator` for tests and benchmarks.

``app.state.orchestrator`` in production is the async DB-backed
:class:`repopulse.pipeline.async_orchestrator.PipelineOrchestrator`.
Callers that cannot spin up Postgres (unit gate, ``benchmark`` harness)
use this factory: same async class, fake repos over shared in-memory
state.

Why not monkeypatch real repos? Production repos need a live
``AsyncSession``. The orchestrator only needs each repo's async API
shape, so duck-typed factories are the cleanest seam.

Semantics (aligned with the async orchestrator + v1.1 behavior):

- Same return shapes (domain dataclasses).
- Duplicate ``event_id`` on ``ingest`` → ``None``.
- Duplicate incident ``signature_hash`` on ``evaluate`` → skip insert.
- R1 fallback → ``observe`` row in action history.
- **Unbounded** in-memory state (no ``deque(maxlen=...)``); retention is
  a DB / ops concern (M3.2).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.correlation.engine import Incident
from repopulse.pipeline.async_orchestrator import PipelineOrchestrator
from repopulse.pipeline.normalize import NormalizedEvent
from repopulse.pipeline.types import ActionHistoryEntry
from repopulse.recommend.engine import Recommendation

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------


@dataclass
class InMemoryState:
    """One bag of state shared across the fake repos for one orchestrator.

    Tests reach into this directly to assert post-conditions
    (e.g. ``state.recommendations[rec_id].state == "approved"``).
    """

    raw_events: dict[UUID, EventEnvelope] = field(default_factory=dict)
    normalized_events: dict[UUID, NormalizedEvent] = field(default_factory=dict)
    anomalies_by_id: dict[UUID, Anomaly] = field(default_factory=dict)
    anomaly_insert_order: list[UUID] = field(default_factory=list)
    incidents: dict[UUID, Incident] = field(default_factory=dict)
    incident_signatures: set[str] = field(default_factory=set)
    incident_insert_order: list[UUID] = field(default_factory=list)
    incident_event_ids: dict[UUID, list[UUID]] = field(default_factory=dict)
    incident_anomaly_ids: dict[UUID, list[UUID]] = field(default_factory=dict)
    recommendations: dict[UUID, Recommendation] = field(default_factory=dict)
    rec_insert_order: list[UUID] = field(default_factory=list)
    rec_to_incident_ended_at: dict[UUID, datetime] = field(default_factory=dict)
    transitions: list[dict[str, Any]] = field(default_factory=list)
    action_history: list[ActionHistoryEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Fake session machinery
# ---------------------------------------------------------------------------


class _FakeSession:
    """Sentinel passed through repo factories — fakes ignore it."""


class _FakeSessionMaker:
    """Async-context-manager-shaped stand-in for ``async_sessionmaker``.

    Every ``begin()`` enters a no-op transaction; the orchestrator
    treats it the same as a real one. The fakes don't need rollback
    behavior because they only mutate after a successful path.
    """

    def begin(self) -> Any:
        @asynccontextmanager
        async def _ctx() -> Any:
            yield _FakeSession()

        return _ctx()


# ---------------------------------------------------------------------------
# Fake repos
# ---------------------------------------------------------------------------


class _FakeEventRepo:
    def __init__(self, state: InMemoryState, _session: Any) -> None:
        self._s = state

    async def insert_raw_idempotent(
        self,
        envelope: EventEnvelope,
        *,
        received_at: datetime,
        occurred_at: datetime,
    ) -> bool:
        if envelope.event_id in self._s.raw_events:
            return False
        self._s.raw_events[envelope.event_id] = envelope
        return True

    async def insert_normalized(self, event: NormalizedEvent) -> None:
        self._s.normalized_events[event.event_id] = event

    async def count_normalized(self) -> int:
        return len(self._s.normalized_events)

    async def list_recent_normalized(
        self, *, limit: int = 1000
    ) -> list[NormalizedEvent]:
        items = sorted(
            self._s.normalized_events.values(), key=lambda e: e.received_at
        )
        return items[-limit:]


class _FakeAnomalyRepo:
    def __init__(self, state: InMemoryState, _session: Any) -> None:
        self._s = state

    async def insert_many(self, anomalies: Any) -> list[UUID]:
        ids: list[UUID] = []
        for a in anomalies:
            aid = uuid4()
            self._s.anomalies_by_id[aid] = a
            self._s.anomaly_insert_order.append(aid)
            ids.append(aid)
        return ids

    async def count(self) -> int:
        return len(self._s.anomalies_by_id)

    async def list_recent_with_ids(
        self, *, limit: int = 200
    ) -> list[tuple[UUID, Anomaly]]:
        ordered = sorted(
            self._s.anomalies_by_id.items(),
            key=lambda kv: kv[1].timestamp,
        )
        return ordered[-limit:]


class _FakeIncidentRepo:
    def __init__(self, state: InMemoryState, _session: Any) -> None:
        self._s = state

    async def insert_with_signature(
        self,
        incident: Incident,
        *,
        signature_hash: str,
        anomaly_ids: Any,
    ) -> bool:
        if signature_hash in self._s.incident_signatures:
            return False
        self._s.incident_signatures.add(signature_hash)
        self._s.incidents[incident.incident_id] = incident
        self._s.incident_insert_order.append(incident.incident_id)
        self._s.incident_event_ids[incident.incident_id] = [
            e.event_id for e in incident.events
        ]
        self._s.incident_anomaly_ids[incident.incident_id] = list(anomaly_ids)
        return True

    async def count(self) -> int:
        return len(self._s.incidents)

    async def list_recent(self, *, limit: int = 100) -> list[Incident]:
        ordered = sorted(
            self._s.incidents.values(),
            key=lambda inc: inc.ended_at,
            reverse=True,
        )
        return ordered[:limit]

    async def list_recent_with_counts(
        self, *, limit: int = 100
    ) -> list[tuple[Incident, int, int]]:
        ordered = sorted(
            self._s.incidents.values(),
            key=lambda inc: inc.ended_at,
            reverse=True,
        )[:limit]
        return [
            (
                inc,
                len(self._s.incident_anomaly_ids.get(inc.incident_id, [])),
                len(self._s.incident_event_ids.get(inc.incident_id, [])),
            )
            for inc in ordered
        ]


class _FakeRecommendationRepo:
    def __init__(self, state: InMemoryState, _session: Any) -> None:
        self._s = state

    async def insert(self, rec: Recommendation) -> None:
        self._s.recommendations[rec.recommendation_id] = rec
        self._s.rec_insert_order.append(rec.recommendation_id)
        inc = self._s.incidents.get(rec.incident_id)
        if inc is not None:
            self._s.rec_to_incident_ended_at[rec.recommendation_id] = inc.ended_at

    async def count(self) -> int:
        return len(self._s.recommendations)

    async def list_latest(self, limit: int = 10) -> list[Recommendation]:
        ranked = sorted(
            self._s.recommendations.values(),
            key=lambda rec: self._s.rec_to_incident_ended_at.get(
                rec.recommendation_id, datetime.min.replace(tzinfo=UTC)
            ),
            reverse=True,
        )
        return ranked[:limit]

    async def find_by_id(self, rec_id: UUID) -> Recommendation | None:
        return self._s.recommendations.get(rec_id)

    async def update_state(
        self,
        rec_id: UUID,
        *,
        to_state: str,
        actor: str,
        reason: str | None = None,
        at: datetime | None = None,
    ) -> Recommendation:
        existing = self._s.recommendations.get(rec_id)
        if existing is None:
            raise KeyError(rec_id)
        if existing.state != "pending":
            raise ValueError(
                f"cannot transition state {existing.state!r} → {to_state!r}; "
                "only pending → approved|rejected is allowed"
            )
        updated = replace(existing, state=to_state)  # type: ignore[arg-type]
        self._s.recommendations[rec_id] = updated
        self._s.transitions.append(
            {
                "recommendation_id": rec_id,
                "from_state": existing.state,
                "to_state": to_state,
                "actor": actor,
                "reason": reason,
                "at": at if at is not None else datetime.now(UTC),
            }
        )
        return updated


class _FakeActionHistoryRepo:
    def __init__(self, state: InMemoryState, _session: Any) -> None:
        self._s = state

    async def append(
        self,
        *,
        at: datetime,
        kind: str,
        recommendation_id: UUID | None,
        actor: str,
        summary: str = "",
    ) -> None:
        self._s.action_history.append(
            ActionHistoryEntry(
                at=at,
                kind=kind,  # type: ignore[arg-type]
                recommendation_id=recommendation_id,
                actor=actor,
                summary=summary,
            )
        )

    async def list_latest(self, limit: int = 50) -> list[ActionHistoryEntry]:
        return list(reversed(self._s.action_history))[:limit]


def make_inmem_orchestrator(
    *, clock: Any = None
) -> tuple[PipelineOrchestrator, InMemoryState]:
    """Build async :class:`PipelineOrchestrator` with fake in-memory repos."""
    state = InMemoryState()
    session_maker = _FakeSessionMaker()
    return (
        PipelineOrchestrator(
            session_maker=session_maker,  # type: ignore[arg-type]
            event_repo_factory=lambda s: _FakeEventRepo(state, s),  # type: ignore[arg-type, return-value]
            anomaly_repo_factory=lambda s: _FakeAnomalyRepo(state, s),  # type: ignore[arg-type, return-value]
            incident_repo_factory=lambda s: _FakeIncidentRepo(state, s),  # type: ignore[arg-type, return-value]
            recommendation_repo_factory=lambda s: _FakeRecommendationRepo(state, s),  # type: ignore[arg-type, return-value]
            action_history_repo_factory=lambda s: _FakeActionHistoryRepo(state, s),  # type: ignore[arg-type, return-value]
            **({"clock": clock} if clock is not None else {}),
        ),
        state,
    )

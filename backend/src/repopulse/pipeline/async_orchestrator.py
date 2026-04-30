"""Async pipeline orchestrator — DB-backed facade over the T4 repositories.

PostgreSQL-backed (or in-memory-fake) pipeline storage. The public
shape (return types) is preserved: callers still get
:class:`NormalizedEvent`, :class:`Recommendation`, :class:`Incident`,
:class:`ActionHistoryEntry` — the same domain dataclasses they got from
the legacy class — so the API contract does not change at this layer.

What changes:

- Every public method is **async**. Callers (FastAPI routes, T6 wiring)
  must ``await``.
- Each method opens its own transaction via
  ``async with self._session_maker.begin() as session``. We do not leak
  a session across logical operations: ``ingest`` is one transaction,
  ``record_anomalies`` is another, ``evaluate`` is another. The one
  documented exception is :meth:`transition_recommendation`, which
  performs UPDATE recommendations + INSERT recommendation_transitions +
  INSERT action_history in a SINGLE transaction so the operator can
  never observe a half-applied approve/reject.
- Repos are injected through factory callables so unit tests can
  substitute in-memory fakes without touching SQLAlchemy.

Order of writes inside ``evaluate``:
1. Load anomalies + events (read).
2. Correlate in-memory (pure function).
3. For each candidate incident, attempt
   ``IncidentRepository.insert_with_signature`` — the
   ``ON CONFLICT (signature_hash) DO NOTHING`` clause makes this the
   atomic dedup gate. Bridge rows (``incident_events`` / ``incident_anomalies``)
   are written by the repo in the same transaction.
4. Only on a fresh insert: emit the recommendation via
   :class:`RecommendationRepository`, and on R1 fallback append an
   ``observe`` row via :class:`ActionHistoryRepository`.

Tech debt acknowledged in T5 handoff:
- :meth:`latest_recommendations` orders by ``IncidentORM.ended_at``
  because ``recommendations`` has no ``created_at`` column. A follow-up
  migration may add ``created_at`` if the join becomes a hot path.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.correlation.engine import Incident, correlate
from repopulse.db.repository import (
    ActionHistoryRepository,
    AnomalyRepository,
    EventRepository,
    IncidentRepository,
    RecommendationRepository,
)
from repopulse.pipeline.normalize import NormalizedEvent, normalize
from repopulse.pipeline.types import (
    ActionHistoryEntry,
    anomaly_fingerprint,
    compute_signature_hash,
)
from repopulse.recommend.engine import Recommendation, State, recommend

EventRepoFactory = Callable[[AsyncSession], EventRepository]
AnomalyRepoFactory = Callable[[AsyncSession], AnomalyRepository]
IncidentRepoFactory = Callable[[AsyncSession], IncidentRepository]
RecommendationRepoFactory = Callable[[AsyncSession], RecommendationRepository]
ActionHistoryRepoFactory = Callable[[AsyncSession], ActionHistoryRepository]
ClockFn = Callable[[], datetime]


def _default_clock() -> datetime:
    return datetime.now(tz=UTC)


class PipelineOrchestrator:
    """Async facade over the persistent storage layer.

    Construct with a :class:`async_sessionmaker` plus per-repo factories.
    Production callers (T6) will use a single set of factories that just
    call the repo classes; tests pass fake factories that close over
    in-memory state. The clock is injectable so tests can pin
    ``datetime.now``.
    """

    def __init__(
        self,
        *,
        session_maker: async_sessionmaker[AsyncSession],
        event_repo_factory: EventRepoFactory = EventRepository,
        anomaly_repo_factory: AnomalyRepoFactory = AnomalyRepository,
        incident_repo_factory: IncidentRepoFactory = IncidentRepository,
        recommendation_repo_factory: RecommendationRepoFactory = (
            RecommendationRepository
        ),
        action_history_repo_factory: ActionHistoryRepoFactory = (
            ActionHistoryRepository
        ),
        clock: ClockFn = _default_clock,
    ) -> None:
        self._session_maker = session_maker
        self._event_repo_factory = event_repo_factory
        self._anomaly_repo_factory = anomaly_repo_factory
        self._incident_repo_factory = incident_repo_factory
        self._recommendation_repo_factory = recommendation_repo_factory
        self._action_history_repo_factory = action_history_repo_factory
        self._clock = clock

    # ------------------------------------------------------------------ ingest

    async def ingest(
        self,
        envelope: EventEnvelope,
        *,
        received_at: datetime | None = None,
    ) -> NormalizedEvent | None:
        """Persist raw + normalized event for ``envelope``; return the
        normalized event, or ``None`` if the ``event_id`` was already
        ingested (idempotent skip — preserves v1.1's ``_seen_keys``
        per-event semantics).
        """
        ts = received_at if received_at is not None else self._clock()
        normalized = normalize(envelope, received_at=ts)
        async with self._session_maker.begin() as session:
            inserted = await self._event_repo_factory(
                session
            ).insert_raw_idempotent(
                envelope, received_at=ts, occurred_at=normalized.occurred_at
            )
            if not inserted:
                return None
            await self._event_repo_factory(session).insert_normalized(
                normalized
            )
        return normalized

    async def record_anomalies(
        self, anomalies: Iterable[Anomaly]
    ) -> list[UUID]:
        """Persist a batch of anomalies; return the minted DB IDs.

        Returned IDs are useful only to the caller that needs them for
        bridge wiring outside ``evaluate`` (none today, but kept on the
        public surface to mirror the repo).
        """
        items = list(anomalies)
        if not items:
            return []
        async with self._session_maker.begin() as session:
            return await self._anomaly_repo_factory(session).insert_many(items)

    async def record_normalized(self, event: NormalizedEvent) -> None:
        """Persist an already-normalized event (e.g. agentic-workflow path).

        The caller has already minted ``event.event_id``; we still need
        a corresponding ``raw_events`` anchor so the FK on
        ``normalized_events.event_id`` is satisfied.
        """
        async with self._session_maker.begin() as session:
            repo = self._event_repo_factory(session)
            await repo.insert_raw_idempotent(
                EventEnvelope(
                    event_id=event.event_id,
                    source=event.source,
                    kind=event.kind,
                    payload=dict(event.attributes),
                ),
                received_at=event.received_at,
                occurred_at=event.occurred_at,
            )
            await repo.insert_normalized(event)

    async def record_workflow_run(
        self,
        *,
        workflow_name: str,
        run_id: int,
        conclusion: str,
        at: datetime,
    ) -> None:
        """Append a ``workflow-run`` action-history row (M5 source)."""
        async with self._session_maker.begin() as session:
            await self._action_history_repo_factory(session).append(
                at=at,
                kind="workflow-run",
                recommendation_id=None,
                actor=workflow_name,
                summary=f"run {run_id}: {conclusion}",
            )

    # ----------------------------------------------------------------- evaluate

    async def evaluate(
        self,
        *,
        window_seconds: float = 300.0,
    ) -> list[Recommendation]:
        """Correlate current state, emit one recommendation per fresh incident.

        Idempotency: ``IncidentRepository.insert_with_signature`` is the
        atomic dedup gate (UNIQUE on ``signature_hash``). A re-evaluation
        over overlapping windows therefore produces ``[]`` for the
        already-seen incidents — same observable behavior as v1.1's
        ``_seen_keys`` LRU.
        """
        async with self._session_maker.begin() as session:
            event_repo = self._event_repo_factory(session)
            anomaly_repo = self._anomaly_repo_factory(session)
            incident_repo = self._incident_repo_factory(session)
            rec_repo = self._recommendation_repo_factory(session)
            history_repo = self._action_history_repo_factory(session)

            anomalies_with_ids = await anomaly_repo.list_recent_with_ids()
            anomaly_id_by_fp: dict[tuple[datetime, float, str], UUID] = {
                anomaly_fingerprint(a): aid for aid, a in anomalies_with_ids
            }
            anomalies = [a for _, a in anomalies_with_ids]
            events = await event_repo.list_recent_normalized()

            incidents = correlate(
                anomalies=anomalies,
                events=events,
                window_seconds=window_seconds,
            )
            new_recs: list[Recommendation] = []
            for incident in incidents:
                signature_hash = compute_signature_hash(incident)
                anomaly_ids = [
                    anomaly_id_by_fp[anomaly_fingerprint(a)]
                    for a in incident.anomalies
                ]
                inserted = await incident_repo.insert_with_signature(
                    incident,
                    signature_hash=signature_hash,
                    anomaly_ids=anomaly_ids,
                )
                if not inserted:
                    continue
                rec = recommend(incident)
                await rec_repo.insert(rec)
                if rec.state == "observed":
                    await history_repo.append(
                        at=self._clock(),
                        kind="observe",
                        recommendation_id=rec.recommendation_id,
                        actor="system",
                        summary="R1 fallback: auto-observed",
                    )
                new_recs.append(rec)
            return new_recs

    # -------------------------------------------------------------------- reads

    async def latest_recommendations(
        self, limit: int = 10
    ) -> list[Recommendation]:
        if limit < 0:
            raise ValueError(f"limit must be >= 0, got {limit!r}")
        async with self._session_maker.begin() as session:
            return await self._recommendation_repo_factory(
                session
            ).list_latest(limit)

    async def latest_incidents(self, limit: int = 50) -> list[Incident]:
        if limit < 0:
            raise ValueError(f"limit must be >= 0, got {limit!r}")
        async with self._session_maker.begin() as session:
            return await self._incident_repo_factory(session).list_recent(
                limit=limit
            )

    async def latest_incidents_with_counts(
        self, limit: int = 50
    ) -> list[tuple[Incident, int, int]]:
        """Like :meth:`latest_incidents`, but returns
        ``(incident, anomaly_count, event_count)`` triples. The dashboard
        incidents endpoint uses this so it can surface counts without
        round-tripping the bridge tables a second time.
        """
        if limit < 0:
            raise ValueError(f"limit must be >= 0, got {limit!r}")
        async with self._session_maker.begin() as session:
            return await self._incident_repo_factory(
                session
            ).list_recent_with_counts(limit=limit)

    async def latest_actions(
        self, limit: int = 50
    ) -> list[ActionHistoryEntry]:
        if limit < 0:
            raise ValueError(f"limit must be >= 0, got {limit!r}")
        async with self._session_maker.begin() as session:
            return await self._action_history_repo_factory(
                session
            ).list_latest(limit)

    async def iter_events(self) -> list[NormalizedEvent]:
        """Snapshot of recent normalized events, oldest-first."""
        async with self._session_maker.begin() as session:
            return await self._event_repo_factory(session).list_recent_normalized()

    async def find_recommendation(
        self, rec_id: UUID
    ) -> Recommendation | None:
        async with self._session_maker.begin() as session:
            return await self._recommendation_repo_factory(
                session
            ).find_by_id(rec_id)

    async def get_recommendation_state(self, rec_id: UUID) -> State | None:
        rec = await self.find_recommendation(rec_id)
        return rec.state if rec is not None else None

    # ------------------------------------------------------------- transitions

    async def transition_recommendation(
        self,
        rec_id: UUID,
        *,
        to_state: Literal["approved", "rejected"],
        actor: str,
        reason: str | None = None,
    ) -> Recommendation:
        """Atomically transition a pending recommendation + emit audit rows.

        Single transaction:
        1. ``RecommendationRepository.update_state`` — UPDATE state +
           INSERT recommendation_transitions row.
        2. ``ActionHistoryRepository.append`` — INSERT action_history row.

        Raises ``KeyError`` if ``rec_id`` does not exist; ``ValueError``
        if the current state is not ``pending``.
        """
        at = self._clock()
        async with self._session_maker.begin() as session:
            updated = await self._recommendation_repo_factory(
                session
            ).update_state(
                rec_id,
                to_state=to_state,
                actor=actor,
                reason=reason,
                at=at,
            )
            await self._action_history_repo_factory(session).append(
                at=at,
                kind="approve" if to_state == "approved" else "reject",
                recommendation_id=rec_id,
                actor=actor,
                summary=reason or "",
            )
            return updated

    # -------------------------------------------------------------- diagnostics

    async def snapshot(self) -> dict[str, int]:
        """Counts for /healthz-style diagnostics. Cheap aggregates only.

        Routes through repository ``count()`` methods so the in-memory
        test fakes can answer without a SQL session.
        """
        async with self._session_maker.begin() as session:
            return {
                "events": await self._event_repo_factory(
                    session
                ).count_normalized(),
                "anomalies": await self._anomaly_repo_factory(session).count(),
                "incidents": await self._incident_repo_factory(session).count(),
                "recommendations": await self._recommendation_repo_factory(
                    session
                ).count(),
            }


__all__ = [
    "ActionHistoryRepoFactory",
    "AnomalyRepoFactory",
    "ClockFn",
    "EventRepoFactory",
    "IncidentRepoFactory",
    "PipelineOrchestrator",
    "RecommendationRepoFactory",
]

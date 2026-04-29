"""In-memory pipeline orchestrator: ingest -> normalize -> store; on demand
correlate over current state and emit recommendations for *previously
unseen* incidents only.

Bounded ``deque``s cap memory use. The interface (``ingest``,
``record_anomalies``, ``evaluate``, ``latest_recommendations``) is
intentionally Redis-Streams-shaped so swapping the in-memory store for a
real bus later is a one-file change (see ADR-002).
"""
from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.correlation.engine import Incident, correlate
from repopulse.pipeline.normalize import NormalizedEvent, normalize
from repopulse.pipeline.types import (
    ActionHistoryEntry,
    _AnomalyFingerprint,
    _incident_key,
    _IncidentKey,
)
from repopulse.recommend.engine import Recommendation, State, recommend

# Re-exported for backward compatibility — pre-T5 callers imported these
# names from this module. Canonical home is :mod:`pipeline.types`.
__all__ = [
    "ActionHistoryEntry",
    "PipelineOrchestrator",
    "_AnomalyFingerprint",
    "_IncidentKey",
    "_incident_key",
]


class PipelineOrchestrator:
    """Glues normalize → correlate → recommend over an in-memory store."""

    def __init__(
        self,
        *,
        max_events: int = 1000,
        max_anomalies: int = 200,
        max_incidents: int = 100,
        max_recommendations: int = 50,
    ) -> None:
        self._events: deque[NormalizedEvent] = deque(maxlen=max_events)
        self._anomalies: deque[Anomaly] = deque(maxlen=max_anomalies)
        self._incidents: deque[Incident] = deque(maxlen=max_incidents)
        # Newest first: appendleft on each evaluate() call.
        self._recommendations: deque[Recommendation] = deque(
            maxlen=max_recommendations
        )
        # LRU-ish set of incident keys we've already emitted for. Bounded
        # to ``max_incidents`` so the dedup state cannot leak unboundedly.
        self._seen_keys: deque[_IncidentKey] = deque(maxlen=max_incidents)
        self._seen_keys_set: set[_IncidentKey] = set()
        # M4: action history (operator approvals + agentic workflow runs).
        self._action_history: deque[ActionHistoryEntry] = deque(maxlen=200)
        # M4: per-recommendation state overlay so the immutable
        # Recommendation dataclass stays immutable.
        self._rec_state: dict[UUID, State] = {}

    def ingest(
        self,
        envelope: EventEnvelope,
        *,
        received_at: datetime | None = None,
    ) -> NormalizedEvent:
        ts = received_at if received_at is not None else datetime.now(tz=UTC)
        event = normalize(envelope, received_at=ts)
        self._events.append(event)
        return event

    def record_anomalies(self, anomalies: Iterable[Anomaly]) -> None:
        for anomaly in anomalies:
            self._anomalies.append(anomaly)

    def record_normalized(self, event: NormalizedEvent) -> None:
        """Append an already-normalized event to the store.

        Used by callers that produce a :class:`NormalizedEvent` directly
        (for example, the agentic-workflow usage endpoint), bypassing the
        ``EventEnvelope -> normalize`` step that :meth:`ingest` runs.
        """
        self._events.append(event)

    def record_workflow_run(
        self,
        *,
        workflow_name: str,
        run_id: int,
        conclusion: str,
        at: datetime,
    ) -> None:
        """Append a ``workflow-run`` :class:`ActionHistoryEntry`.

        Per ADR-004 §3, agentic workflow runs surface in the same audit
        feed as operator approvals so the dashboard can render both in
        one timeline. Called by the M5 ``/api/v1/github/usage`` endpoint
        after the workflow's :class:`NormalizedEvent` lands in the
        orchestrator.
        """
        self._action_history.append(
            ActionHistoryEntry(
                at=at,
                kind="workflow-run",
                recommendation_id=None,
                actor=workflow_name,
                summary=f"run {run_id}: {conclusion}",
            )
        )

    def _register_key(self, key: _IncidentKey) -> bool:
        """Return True iff ``key`` is new. Maintains the bounded LRU set."""
        if key in self._seen_keys_set:
            return False
        if len(self._seen_keys) == self._seen_keys.maxlen:
            evicted = self._seen_keys.popleft()
            self._seen_keys_set.discard(evicted)
        self._seen_keys.append(key)
        self._seen_keys_set.add(key)
        return True

    def evaluate(
        self,
        *,
        window_seconds: float = 300.0,
    ) -> list[Recommendation]:
        """Run correlation over current state and emit one recommendation
        per **newly-seen** incident. Incidents whose content signature has
        already produced a recommendation in this orchestrator's lifetime
        are skipped — calling ``evaluate`` twice with no new input
        therefore returns ``[]`` the second time.

        Returns the new batch only.
        """
        incidents = correlate(
            anomalies=list(self._anomalies),
            events=list(self._events),
            window_seconds=window_seconds,
        )
        new_recs: list[Recommendation] = []
        for incident in incidents:
            key = _incident_key(incident)
            if not self._register_key(key):
                continue
            self._incidents.append(incident)
            rec = recommend(incident)
            # Bounded ``_recommendations`` deque drops the oldest entry on
            # appendleft when full; clean up its state-overlay key so
            # ``_rec_state`` stays bounded along with the deque.
            if len(self._recommendations) == self._recommendations.maxlen:
                evicted = self._recommendations[-1]
                self._rec_state.pop(evicted.recommendation_id, None)
            self._recommendations.appendleft(rec)
            self._rec_state[rec.recommendation_id] = rec.state
            if rec.state == "observed":
                self._action_history.append(
                    ActionHistoryEntry(
                        at=datetime.now(tz=UTC),
                        kind="observe",
                        recommendation_id=rec.recommendation_id,
                        actor="system",
                        summary="R1 fallback: auto-observed",
                    )
                )
            new_recs.append(rec)
        return new_recs

    def latest_recommendations(self, limit: int = 10) -> list[Recommendation]:
        if limit < 0:
            raise ValueError(f"limit must be >= 0, got {limit!r}")
        out: list[Recommendation] = []
        for rec in list(self._recommendations)[:limit]:
            current = self._rec_state.get(rec.recommendation_id, rec.state)
            out.append(rec if current == rec.state else replace(rec, state=current))
        return out

    def latest_incidents(self, limit: int = 50) -> list[Incident]:
        if limit < 0:
            raise ValueError(f"limit must be >= 0, got {limit!r}")
        return list(self._incidents)[-limit:][::-1] if limit else []

    def iter_events(self) -> list[NormalizedEvent]:
        """Snapshot of the events deque, oldest-first.

        Returned as a list so callers can iterate safely even if a
        concurrent ``ingest`` mutates the deque mid-loop. Used by the
        SLO endpoint to compute availability without poking
        ``self._events`` directly.
        """
        return list(self._events)

    def latest_actions(self, limit: int = 50) -> list[ActionHistoryEntry]:
        if limit < 0:
            raise ValueError(f"limit must be >= 0, got {limit!r}")
        return list(self._action_history)[-limit:][::-1] if limit else []

    def get_recommendation_state(self, rec_id: UUID) -> State | None:
        return self._rec_state.get(rec_id)

    def find_recommendation(self, rec_id: UUID) -> Recommendation | None:
        for rec in self._recommendations:
            if rec.recommendation_id == rec_id:
                state = self._rec_state.get(rec_id, rec.state)
                return replace(rec, state=state)
        return None

    def transition_recommendation(
        self,
        rec_id: UUID,
        *,
        to_state: Literal["approved", "rejected"],
        actor: str,
        reason: str | None = None,
    ) -> Recommendation:
        """Transition a pending recommendation to ``approved`` or ``rejected``.

        Raises ``KeyError`` if the recommendation does not exist;
        ``ValueError`` if the current state is not ``pending``.
        """
        rec = self.find_recommendation(rec_id)
        if rec is None:
            raise KeyError(rec_id)
        current = self._rec_state.get(rec_id, rec.state)
        if current != "pending":
            raise ValueError(
                f"cannot transition state {current!r} → {to_state!r}; "
                "only pending → approved|rejected is allowed"
            )
        self._rec_state[rec_id] = to_state
        self._action_history.append(
            ActionHistoryEntry(
                at=datetime.now(tz=UTC),
                kind="approve" if to_state == "approved" else "reject",
                recommendation_id=rec_id,
                actor=actor,
                summary=reason or "",
            )
        )
        return replace(rec, state=to_state)

    def snapshot(self) -> dict[str, int]:
        return {
            "events": len(self._events),
            "anomalies": len(self._anomalies),
            "incidents": len(self._incidents),
            "recommendations": len(self._recommendations),
        }

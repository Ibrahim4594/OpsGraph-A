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
from datetime import UTC, datetime
from uuid import UUID

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.correlation.engine import Incident, correlate
from repopulse.pipeline.normalize import NormalizedEvent, normalize
from repopulse.recommend.engine import Recommendation, recommend

_AnomalyFingerprint = tuple[datetime, float, str]
_IncidentKey = tuple[frozenset[UUID], frozenset[_AnomalyFingerprint]]


def _incident_key(incident: Incident) -> _IncidentKey:
    """Stable, content-derived signature for ``incident``.

    Two incidents with the same set of underlying events and anomalies
    produce the same key, even though their freshly-generated UUIDs
    differ. Used by ``PipelineOrchestrator`` to dedupe recommendations
    across repeated ``evaluate`` calls on overlapping inputs.
    """
    events_key = frozenset(e.event_id for e in incident.events)
    anomalies_key: frozenset[_AnomalyFingerprint] = frozenset(
        (a.timestamp, a.value, a.series_name) for a in incident.anomalies
    )
    return (events_key, anomalies_key)


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
            self._recommendations.appendleft(rec)
            new_recs.append(rec)
        return new_recs

    def latest_recommendations(self, limit: int = 10) -> list[Recommendation]:
        if limit < 0:
            raise ValueError(f"limit must be >= 0, got {limit!r}")
        return list(self._recommendations)[:limit]

    def snapshot(self) -> dict[str, int]:
        return {
            "events": len(self._events),
            "anomalies": len(self._anomalies),
            "incidents": len(self._incidents),
            "recommendations": len(self._recommendations),
        }

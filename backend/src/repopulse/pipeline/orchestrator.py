"""In-memory pipeline orchestrator: ingest -> normalize -> store; on demand
correlate over current state and emit recommendations.

Bounded ``deque``s cap memory use. The interface (``ingest``,
``record_anomalies``, ``evaluate``, ``latest_recommendations``) is
intentionally Redis-Streams-shaped so swapping the in-memory store for a
real bus later is a one-file change (see ADR-002).
"""
from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from datetime import UTC, datetime

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.correlation.engine import Incident, correlate
from repopulse.pipeline.normalize import NormalizedEvent, normalize
from repopulse.recommend.engine import Recommendation, recommend


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

    def evaluate(
        self,
        *,
        window_seconds: float = 300.0,
    ) -> list[Recommendation]:
        """Run correlation over current state and emit one recommendation per
        incident. Returned recommendations are also stashed in the latest-first
        queue. Returns the new batch only."""
        incidents = correlate(
            anomalies=list(self._anomalies),
            events=list(self._events),
            window_seconds=window_seconds,
        )
        new_recs: list[Recommendation] = []
        for incident in incidents:
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

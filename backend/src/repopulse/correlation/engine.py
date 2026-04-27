"""Correlation: merge anomalies + events into a single sorted timeline,
then group consecutive items whose gap is within ``window_seconds``."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from repopulse.anomaly.detector import Anomaly
from repopulse.pipeline.normalize import NormalizedEvent


@dataclass(frozen=True)
class Incident:
    incident_id: UUID
    started_at: datetime
    ended_at: datetime
    sources: tuple[str, ...]
    anomalies: tuple[Anomaly, ...]
    events: tuple[NormalizedEvent, ...]


@dataclass
class _Bucket:
    """Mutable scratch state while we walk the timeline."""

    started_at: datetime
    ended_at: datetime
    anomalies: list[Anomaly] = field(default_factory=list)
    events: list[NormalizedEvent] = field(default_factory=list)
    sources: set[str] = field(default_factory=set)


def _timestamp_of(item: Anomaly | NormalizedEvent) -> datetime:
    return item.timestamp if isinstance(item, Anomaly) else item.occurred_at


def _source_of(item: Anomaly | NormalizedEvent) -> str:
    return item.series_name if isinstance(item, Anomaly) else item.source


def _bucket_to_incident(bucket: _Bucket) -> Incident:
    return Incident(
        incident_id=uuid4(),
        started_at=bucket.started_at,
        ended_at=bucket.ended_at,
        sources=tuple(sorted(bucket.sources)),
        anomalies=tuple(bucket.anomalies),
        events=tuple(bucket.events),
    )


def correlate(
    *,
    anomalies: Sequence[Anomaly],
    events: Sequence[NormalizedEvent],
    window_seconds: float = 300.0,
) -> list[Incident]:
    """Group anomalies + events into incident timelines.

    A new incident starts whenever the gap from the previous item to the
    current one strictly exceeds ``window_seconds``. The boundary at
    exactly ``window_seconds`` is inclusive (items still grouped).
    """
    timeline: list[Anomaly | NormalizedEvent] = list(anomalies) + list(events)
    if not timeline:
        return []

    timeline.sort(key=_timestamp_of)

    incidents: list[Incident] = []
    current = _Bucket(
        started_at=_timestamp_of(timeline[0]),
        ended_at=_timestamp_of(timeline[0]),
    )

    def _add(bucket: _Bucket, item: Anomaly | NormalizedEvent) -> None:
        ts = _timestamp_of(item)
        bucket.ended_at = ts
        bucket.sources.add(_source_of(item))
        if isinstance(item, Anomaly):
            bucket.anomalies.append(item)
        else:
            bucket.events.append(item)

    _add(current, timeline[0])

    for item in timeline[1:]:
        gap = (_timestamp_of(item) - current.ended_at).total_seconds()
        if gap <= window_seconds:
            _add(current, item)
        else:
            incidents.append(_bucket_to_incident(current))
            current = _Bucket(
                started_at=_timestamp_of(item),
                ended_at=_timestamp_of(item),
            )
            _add(current, item)

    incidents.append(_bucket_to_incident(current))
    return incidents

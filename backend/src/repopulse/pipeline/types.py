"""Shared types + helpers for the pipeline (orchestrator + repos).

Lives here so the persistence-layer
repository :mod:`db.repository.action_history_repo` can import
:class:`ActionHistoryEntry` without forming an import cycle when the
async :class:`pipeline.async_orchestrator.PipelineOrchestrator` (T5) in
turn imports the repos.

The signature-hash helper is the **content side** of v1.1's in-memory
``_seen_keys`` LRU, lifted into a deterministic 64-char hex digest for
the ``incidents.signature_hash`` UNIQUE constraint introduced in T3.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from repopulse.anomaly.detector import Anomaly
from repopulse.correlation.engine import Incident


@dataclass(frozen=True)
class ActionHistoryEntry:
    """One transition in the operator action history.

    Kinds:
    - ``approve`` / ``reject`` — operator-driven recommendation transition.
    - ``observe`` — system auto-observed an R1 recommendation.
    - ``workflow-run`` — agentic workflow run completed (M5 source).
    """

    at: datetime
    kind: Literal["approve", "reject", "observe", "workflow-run"]
    recommendation_id: UUID | None
    actor: str
    summary: str


_AnomalyFingerprint = tuple[datetime, float, str]
_IncidentKey = tuple[frozenset[UUID], frozenset[_AnomalyFingerprint]]


def _incident_key(incident: Incident) -> _IncidentKey:
    """Stable, content-derived signature for ``incident``.

    Two incidents with the same set of underlying events and anomalies
    produce the same key, even though their freshly-generated UUIDs
    differ. Canonical definition lives in this module (T5 / T11).
    """
    events_key = frozenset(e.event_id for e in incident.events)
    anomalies_key: frozenset[_AnomalyFingerprint] = frozenset(
        (a.timestamp, a.value, a.series_name) for a in incident.anomalies
    )
    return (events_key, anomalies_key)


def anomaly_fingerprint(anomaly: Anomaly) -> _AnomalyFingerprint:
    """Stable per-anomaly fingerprint used both by :func:`_incident_key`
    and by the orchestrator's ``evaluate()`` path to map domain Anomaly
    objects back to their persisted ``anomalies.id`` row IDs."""
    return (anomaly.timestamp, anomaly.value, anomaly.series_name)


def compute_signature_hash(incident: Incident) -> str:
    """Deterministic 64-char SHA-256 hex of an incident's content signature.

    Sorts both the event-ID set and the anomaly-fingerprint set before
    serialising so the resulting hex is reproducible across processes
    and Python versions (frozenset ``repr()`` is not stable).
    """
    event_ids = sorted(str(e.event_id) for e in incident.events)
    fingerprints = sorted(
        [a.timestamp.isoformat(), a.value, a.series_name]
        for a in incident.anomalies
    )
    payload = json.dumps(
        {"events": event_ids, "anomalies": fingerprints},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "ActionHistoryEntry",
    "anomaly_fingerprint",
    "compute_signature_hash",
    "_incident_key",
    "_IncidentKey",
    "_AnomalyFingerprint",
]

"""Pipeline normalization: EventEnvelope -> NormalizedEvent.

Pure function. No IO. Idempotent.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from repopulse.api.events import EventEnvelope

Severity = Literal["info", "warning", "error", "critical"]
_KNOWN_SOURCES: frozenset[str] = frozenset(
    {"github", "otel-metrics", "otel-logs", "synthetic"}
)
_SEVERITY_VALUES: frozenset[str] = frozenset({"info", "warning", "error", "critical"})


@dataclass(frozen=True)
class NormalizedEvent:
    event_id: UUID
    received_at: datetime
    occurred_at: datetime
    source: str
    kind: str
    severity: Severity
    attributes: dict[str, str]


def _flatten_attributes(payload: dict[str, object]) -> dict[str, str]:
    """Flatten payload values into string-only attributes (span-friendly)."""
    out: dict[str, str] = {}
    for k, v in payload.items():
        if k in ("occurred_at", "severity"):
            continue
        if isinstance(v, str):
            out[k] = v
        elif isinstance(v, bool):
            out[k] = str(v)
        elif isinstance(v, (int, float)):
            out[k] = str(v)
        else:
            out[k] = json.dumps(v, default=str)
    return out


def _resolve_kind(source: str, kind: str) -> str:
    if source == "otel-metrics":
        return "metric-spike"
    if source == "otel-logs":
        return "info-log"  # may be upgraded to "error-log" by severity check
    if source not in _KNOWN_SOURCES:
        return f"unknown-{kind}"
    return kind


def _infer_severity(kind: str, payload_severity: object | None) -> Severity:
    if isinstance(payload_severity, str) and payload_severity in _SEVERITY_VALUES:
        return payload_severity  # type: ignore[return-value]
    if kind in ("ci-failure", "error-log"):
        return "error"
    if kind.startswith("metric-spike"):
        return "warning"
    return "info"


def normalize(envelope: EventEnvelope, *, received_at: datetime) -> NormalizedEvent:
    """Normalize an inbound :class:`EventEnvelope` into a canonical event.

    The function is pure: same input + same ``received_at`` always yields
    the same output. ``received_at`` is supplied by the caller (typically
    the ingest layer) so tests can pin time deterministically.
    """
    payload_obj = envelope.payload
    payload: dict[str, object] = payload_obj if isinstance(payload_obj, dict) else {}

    occurred_raw = payload.get("occurred_at")
    if isinstance(occurred_raw, str):
        occurred_at = datetime.fromisoformat(occurred_raw)
    else:
        occurred_at = received_at

    kind = _resolve_kind(envelope.source, envelope.kind)
    payload_severity = payload.get("severity")
    if envelope.source == "otel-logs" and payload_severity in ("error", "critical"):
        kind = "error-log"
    severity = _infer_severity(kind, payload_severity)

    return NormalizedEvent(
        event_id=envelope.event_id,
        received_at=received_at,
        occurred_at=occurred_at,
        source=envelope.source,
        kind=kind,
        severity=severity,
        attributes=_flatten_attributes(payload),
    )

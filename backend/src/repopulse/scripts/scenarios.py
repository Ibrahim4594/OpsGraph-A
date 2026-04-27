"""Loader for scenarios/*.json — used by the benchmark harness.

Hand-authored JSON files describe a deterministic incident timeline:
- ``events``: list of ``{offset_seconds, source, kind, payload}``.
- ``anomalies``: list of detector outputs with offsets relative to a fixed base.
- ``expected_action_category``: the category the recommendation engine
  should emit; the harness flags any deviation as a false positive.

The loader is strict about ``expected_action_category`` (it must be one
of the four known categories) so a typo in a fixture surfaces immediately
instead of silently inflating the false-positive rate.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.scripts.benchmark import (
    ActionCategory,
    Scenario,
    ScenarioEvent,
)

_AnomalySeverity = Literal["warning", "critical"]

_VALID_CATEGORIES: frozenset[str] = frozenset(
    {"observe", "triage", "escalate", "rollback"}
)
_T_BASE = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)


def load_scenario(path: Path) -> Scenario:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    cat = raw.get("expected_action_category")
    if cat not in _VALID_CATEGORIES:
        raise ValueError(
            "expected_action_category must be one of "
            f"{sorted(_VALID_CATEGORIES)}, got {cat!r}"
        )
    events = [
        ScenarioEvent(
            offset_seconds=float(ev["offset_seconds"]),
            envelope=EventEnvelope.model_validate(
                {
                    "event_id": uuid4(),
                    "source": ev["source"],
                    "kind": ev["kind"],
                    "payload": ev.get("payload", {}),
                }
            ),
        )
        for ev in raw.get("events", [])
    ]
    anomalies = [
        Anomaly(
            timestamp=_T_BASE + timedelta(seconds=float(a["offset_seconds"])),
            value=float(a["value"]),
            baseline_median=float(a["baseline_median"]),
            baseline_mad=float(a["baseline_mad"]),
            score=float(a["score"]),
            severity=cast(_AnomalySeverity, a["severity"]),
            series_name=a["series_name"],
        )
        for a in raw.get("anomalies", [])
    ]
    return Scenario(
        name=str(raw["name"]),
        expected_action_category=cast(ActionCategory, cat),
        events=events,
        anomalies=anomalies,
    )

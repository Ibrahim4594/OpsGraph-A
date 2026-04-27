"""benchmark.py — reproducible KPI harness for the AIOps pipeline.

Drives :class:`PipelineOrchestrator` in-process over a scenario fixture.
Emits one :class:`BenchmarkResult` per scenario and aggregates them via
:func:`summarize`. No I/O beyond reading scenarios and printing JSON; safe
to call from tests.

KPI definitions (also in docs/results-report.md):

- **MTTR** (time-to-recommendation): seconds from the first anomaly's
  ``timestamp`` to the orchestrator's first emitted ``Recommendation``.
  Floors at 0. ``None`` when the scenario has no anomalies.
- **False positive**: ``True`` iff
  ``recommendation.action_category != scenario.expected_action_category``.
- **Burn-rate lead time**: seconds from the first error-classified event
  to the first SLO sample where ``burn_band != "ok"``. ``None`` if no
  error event in the scenario or the band stays ok throughout.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.api.slo import _classify_event
from repopulse.pipeline.orchestrator import PipelineOrchestrator
from repopulse.slo import SLO, availability_sli, burn_rate

# Anchor that ``scenarios.load_scenario`` uses when materialising anomaly
# timestamps from ``offset_seconds`` in the JSON file. Kept in sync here
# because the harness re-anchors anomalies onto the runtime ``now`` so
# correlate() groups them with events ingested at the same ``now`` clock.
_SCENARIO_ANCHOR = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)

ActionCategory = Literal["observe", "triage", "escalate", "rollback"]


@dataclass(frozen=True)
class ScenarioEvent:
    offset_seconds: float
    envelope: EventEnvelope


@dataclass(frozen=True)
class Scenario:
    name: str
    expected_action_category: ActionCategory
    events: list[ScenarioEvent]
    anomalies: list[Anomaly] = field(default_factory=list)


@dataclass(frozen=True)
class BenchmarkResult:
    scenario_name: str
    action_category: str
    expected_action_category: str
    false_positive: bool
    mttr_seconds: float | None
    burn_rate_lead_seconds: float | None


def run_scenario(scenario: Scenario, *, now: datetime) -> BenchmarkResult:
    orch = PipelineOrchestrator()
    for event in scenario.events:
        orch.ingest(
            event.envelope,
            received_at=now + timedelta(seconds=event.offset_seconds),
        )
    # Re-anchor anomaly timestamps to ``now`` so they share the correlation
    # window with the events. The fixture's offset (relative to
    # ``_SCENARIO_ANCHOR``) is preserved.
    rebased_anomalies = [
        replace(anomaly, timestamp=now + (anomaly.timestamp - _SCENARIO_ANCHOR))
        for anomaly in scenario.anomalies
    ]
    if rebased_anomalies:
        orch.record_anomalies(rebased_anomalies)
    orch.evaluate(window_seconds=300.0)

    recs = orch.latest_recommendations(limit=1)
    if not recs:
        return BenchmarkResult(
            scenario_name=scenario.name,
            action_category="observe",
            expected_action_category=scenario.expected_action_category,
            false_positive=scenario.expected_action_category != "observe",
            mttr_seconds=None,
            burn_rate_lead_seconds=None,
        )

    rec = recs[0]

    mttr_seconds: float | None
    if rebased_anomalies:
        first_anomaly_ts = min(anomaly.timestamp for anomaly in rebased_anomalies)
        last_anomaly_ts = max(anomaly.timestamp for anomaly in rebased_anomalies)
        last_event_ts = (
            now + timedelta(seconds=scenario.events[-1].offset_seconds)
            if scenario.events
            else first_anomaly_ts
        )
        # MTTR is "earliest moment a streaming pipeline could emit the
        # recommendation" minus "first anomaly", which is the later of
        # last event arrival and last anomaly arrival.
        trigger_ts = max(last_event_ts, last_anomaly_ts)
        mttr_seconds = max(0.0, (trigger_ts - first_anomaly_ts).total_seconds())
    else:
        mttr_seconds = None

    burn_lead_seconds = _burn_lead_seconds(orch)

    return BenchmarkResult(
        scenario_name=scenario.name,
        action_category=rec.action_category,
        expected_action_category=scenario.expected_action_category,
        false_positive=rec.action_category != scenario.expected_action_category,
        mttr_seconds=mttr_seconds,
        burn_rate_lead_seconds=burn_lead_seconds,
    )


def _burn_lead_seconds(
    orch: PipelineOrchestrator, *, target: float = 0.99
) -> float | None:
    events = orch.iter_events()
    if not events:
        return None
    first_error_at: datetime | None = None
    first_nonok_at: datetime | None = None
    total = errors = 0
    slo = SLO(target=target)
    for event in events:
        total += 1
        if _classify_event(event.kind, event.severity):
            errors += 1
            if first_error_at is None:
                first_error_at = event.received_at
        avail = availability_sli(success_count=total - errors, total_count=total)
        rate = (errors / total) if total else 0.0
        _ = burn_rate(actual_error_rate=rate, slo=slo) if total else 0.0
        over_budget = total > 0 and avail < target
        if over_budget and first_nonok_at is None:
            first_nonok_at = event.received_at
            break
    if first_error_at is None or first_nonok_at is None:
        return None
    return max(0.0, (first_nonok_at - first_error_at).total_seconds())


def summarize(results: list[BenchmarkResult]) -> dict[str, object]:
    total = len(results)
    fp = sum(1 for r in results if r.false_positive)
    mttrs = [r.mttr_seconds for r in results if r.mttr_seconds is not None]
    leads = [
        r.burn_rate_lead_seconds
        for r in results
        if r.burn_rate_lead_seconds is not None
    ]
    return {
        "scenarios": total,
        "false_positives": fp,
        "false_positive_rate": (fp / total) if total else 0.0,
        "mttr_seconds_avg": (sum(mttrs) / len(mttrs)) if mttrs else None,
        "mttr_seconds_max": max(mttrs) if mttrs else None,
        "burn_lead_seconds_avg": (sum(leads) / len(leads)) if leads else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="RepoPulse benchmark harness")
    parser.add_argument("--scenarios-dir", default="scenarios")
    parser.add_argument(
        "--out", default="-", help="output path or '-' for stdout"
    )
    args = parser.parse_args()
    scenario_paths = sorted(Path(args.scenarios_dir).glob("*.json"))
    from repopulse.scripts.scenarios import load_scenario

    now = datetime.now().astimezone()
    results = [run_scenario(load_scenario(p), now=now) for p in scenario_paths]
    payload = {
        "summary": summarize(results),
        "results": [asdict(r) for r in results],
    }
    body = json.dumps(payload, indent=2, default=str)
    if args.out == "-":
        print(body)
    else:
        Path(args.out).write_text(body, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

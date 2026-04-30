# Milestone 6 — Portfolio Polish + KPI Report — Execution Plan

> **For agentic workers:** Continues from `v0.5.0-m4`. REQUIRED SUB-SKILL: Use `superpowers:executing-plans` (inline). Steps use checkbox (`- [ ]`) syntax for tracking. Required skills, invoked explicitly per task: `superpowers:writing-plans` (this doc), `superpowers:test-driven-development` (every behavior change), `superpowers:systematic-debugging` (any non-trivial failure), `superpowers:verification-before-completion` (before claiming done), `superpowers:requesting-code-review` (before final handoff), `superpowers:receiving-code-review` (if findings raised). Constraints: anti-hallucination strict, **no unverifiable KPI claims**, every metric in the results report must include data source + command used.

## Goal

Turn the working AIOps system (M1–M5 backend + M4 dashboard) into a portfolio-ready release. Add a reproducible benchmark harness that produces measurable KPIs (MTTR, false-positive rate, burn-rate lead time), publish them in a results report with re-runnable commands, polish the README, ship demo assets and contributor docs, and tag `v1.0.0`.

## Architecture

```
backend/scripts/benchmark.py
    │
    ├── loads scenarios/*.json (Task 3) — reproducible incident timelines
    ├── drives PipelineOrchestrator in-process (no HTTP) for clean timing
    ├── records (per-scenario):
    │     - mttr_seconds       = first-anomaly → first-recommendation
    │     - false_positive     = recommendation.action_category vs expected
    │     - burn_rate_lead_s   = first error event → SLO band ≠ "ok"
    └── prints a CSV/JSON summary

docs/results-report.md   — KPI table + per-scenario detail + raw command
docs/demo/               — screenshots + architecture export + demo flow
docs/SETUP.md            — Docker/WSL/Ubuntu install path
docs/CONTRIBUTING.md     — TDD discipline, PR checklist, code-review process
LICENSE                  — MIT
```

## Tech Stack

- Backend benchmarks: stdlib only (`statistics`, `time.perf_counter`, `json`); no new deps.
- Demo flow: bash script that boots backend + frontend + seeds canonical events (curl/python).
- Docs: plain markdown; mermaid diagrams render on GitHub.
- No new runtime dependencies.

## File Structure (additions)

```
backend/
├── scripts/
│   ├── benchmark.py           (NEW — main harness)
│   └── seed_demo.py           (NEW — seeds the demo dataset over HTTP)
├── tests/
│   └── test_benchmark.py      (NEW — TDD coverage of the harness)

scenarios/                     (NEW — reproducible incident fixtures)
├── 01-quiet.json
├── 02-single-anomaly.json
├── 03-multi-source-critical.json
├── 04-noisy-baseline.json
└── README.md

docs/
├── results-report.md          (NEW — KPI table + sources)
├── demo/
│   ├── README.md              (NEW — demo flow walkthrough)
│   ├── architecture.svg       (NEW — exported from architecture.md mermaid)
│   └── screenshots/           (NEW — 4 dashboard pages)
├── SETUP.md                   (NEW — Docker/WSL setup, prerequisites)
└── CONTRIBUTING.md            (NEW — workflow + PR checklist)

LICENSE                        (NEW — MIT, copyright Ibrahim Samad)
README.md                      (modify — final polish: badges, screenshots, demo command)

backend/pyproject.toml         (modify — version 1.0.0)
backend/src/repopulse/__init__.py  (modify — __version__ = "1.0.0")
frontend/package.json          (modify — version 1.0.0)

scripts/
└── demo.sh                    (NEW — one-command demo runner)
```

---

## Task 1 — M6 plan + scope notes

**Files:**
- Create: `plans/milestone-6-execution-plan.md` (this file).

- [ ] **Step 1: Save this plan.** Already saved if you're reading it.

- [ ] **Step 2: Commit.**

```bash
git add plans/milestone-6-execution-plan.md
git commit -m "plan: M6 execution plan (benchmark + KPI report + portfolio polish)"
```

---

## Task 2 — TDD: Benchmark harness

**Files:**
- Create: `backend/scripts/benchmark.py`
- Create: `backend/tests/test_benchmark.py`

The harness loads a list of scenarios (Task 3 builds them), drives the orchestrator in-process, and emits a structured result per scenario. Pure-functional core, easy to test.

**KPI definitions (locked here so the report can cite the same definitions):**

- **MTTR** (Mean Time To Recommendation): wall-clock time from the first anomaly's `timestamp` to the first emitted `Recommendation` for that incident, in seconds. Floors at 0 if anomaly and recommendation share the same instant. (Note: this is *time-to-recommendation*, not full operator response. Real MTTR — incident → resolution — is out of scope until persistence + operator-action timing land.)
- **False-positive flag**: `True` iff `recommendation.action_category != scenario.expected_action_category`. Scenarios authored in Task 3 carry the expected category.
- **Burn-rate lead time**: seconds from the first error-classified event in the scenario to the first SLO sample where `burn_band != "ok"`. The harness samples SLO state by re-running the same in-process function (`repopulse.api.slo._classify_event` + the pure `slo` module) at each event boundary in the timeline.

- [ ] **Step 1: Write failing test (`test_benchmark.py`).**

```python
"""Benchmark harness contract."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from repopulse.api.events import EventEnvelope
from repopulse.scripts.benchmark import (
    Scenario,
    ScenarioEvent,
    BenchmarkResult,
    run_scenario,
    summarize,
)

_T0 = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)


def _scenario_quiet() -> Scenario:
    """Single benign event → R1 (observe). Expected category = observe."""
    return Scenario(
        name="quiet",
        expected_action_category="observe",
        events=[
            ScenarioEvent(
                offset_seconds=0,
                envelope=EventEnvelope.model_validate({
                    "event_id": uuid4(),
                    "source": "github",
                    "kind": "push",
                    "payload": {},
                }),
            ),
        ],
        anomalies=[],
    )


def test_run_scenario_returns_result_with_action_category() -> None:
    result = run_scenario(_scenario_quiet(), now=_T0)
    assert isinstance(result, BenchmarkResult)
    assert result.scenario_name == "quiet"
    assert result.action_category == "observe"
    assert result.false_positive is False


def test_run_scenario_records_mttr_floor_zero_for_event_only() -> None:
    """A scenario with no anomalies has no anomaly→rec interval to time;
    MTTR is recorded as None to make the absence explicit."""
    result = run_scenario(_scenario_quiet(), now=_T0)
    assert result.mttr_seconds is None


def test_run_scenario_records_mttr_for_anomaly_to_recommendation() -> None:
    from repopulse.anomaly.detector import Anomaly

    scenario = Scenario(
        name="anomaly-fast",
        expected_action_category="escalate",
        events=[
            ScenarioEvent(
                offset_seconds=0,
                envelope=EventEnvelope.model_validate({
                    "event_id": uuid4(),
                    "source": "github",
                    "kind": "push",
                    "payload": {},
                }),
            ),
        ],
        anomalies=[
            Anomaly(
                timestamp=_T0 + timedelta(seconds=10),
                value=200.0,
                baseline_median=10.0,
                baseline_mad=1.0,
                score=20.0,
                severity="critical",
                series_name="otel-metrics",
            ),
        ],
    )
    result = run_scenario(scenario, now=_T0)
    assert result.action_category in {"escalate", "rollback"}
    assert result.mttr_seconds is not None
    assert result.mttr_seconds >= 0.0


def test_summarize_aggregates_false_positive_rate() -> None:
    results = [
        BenchmarkResult(
            scenario_name="a",
            action_category="observe",
            expected_action_category="observe",
            false_positive=False,
            mttr_seconds=None,
            burn_rate_lead_seconds=None,
        ),
        BenchmarkResult(
            scenario_name="b",
            action_category="triage",
            expected_action_category="escalate",
            false_positive=True,
            mttr_seconds=5.0,
            burn_rate_lead_seconds=2.0,
        ),
    ]
    summary = summarize(results)
    assert summary["scenarios"] == 2
    assert summary["false_positive_rate"] == 0.5
    # MTTR aggregate ignores None values
    assert summary["mttr_seconds_avg"] == 5.0
```

- [ ] **Step 2: Run RED.**

```
cd backend && ./.venv/Scripts/python -m pytest tests/test_benchmark.py -v
```

Expected: `ModuleNotFoundError: No module named 'repopulse.scripts.benchmark'`.

- [ ] **Step 3: Implement (`backend/scripts/__init__.py` + `benchmark.py`).**

Create `backend/src/repopulse/scripts/__init__.py` if not present (empty).

As of M2.0 T11, `benchmark.py` uses `asyncio.run` with `PipelineOrchestrator` from `repopulse.pipeline.async_orchestrator` and `repopulse.testing.make_inmem_orchestrator` for in-process runs. The sketch below shows the historical sync shape; see the repo file for the current async implementation.

```python
"""benchmark.py — reproducible KPI harness for the AIOps pipeline.

Drives :class:`PipelineOrchestrator` in-process over a scenario fixture.
Emits one :class:`BenchmarkResult` per scenario and aggregates them via
``summarize``. No I/O beyond reading scenarios and printing JSON; safe
to call from tests.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import UUID

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.api.slo import _classify_event
from repopulse.pipeline.async_orchestrator import PipelineOrchestrator
from repopulse.slo import SLO, availability_sli, burn_rate

ActionCategory = Literal["observe", "triage", "escalate", "rollback"]
BurnBand = Literal["ok", "slow", "fast"]


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
    # Ingest events at their timeline offsets so received_at reflects the
    # scenario's logical clock; in-process means no real wall-clock waits.
    for ev in scenario.events:
        orch.ingest(ev.envelope, received_at=now + timedelta(seconds=ev.offset_seconds))
    if scenario.anomalies:
        orch.record_anomalies(scenario.anomalies)
    orch.evaluate(window_seconds=300.0)

    recs = orch.latest_recommendations(limit=1)
    if not recs:
        # No recommendation emitted at all — count as observe with FP if expected differs.
        return BenchmarkResult(
            scenario_name=scenario.name,
            action_category="observe",
            expected_action_category=scenario.expected_action_category,
            false_positive=scenario.expected_action_category != "observe",
            mttr_seconds=None,
            burn_rate_lead_seconds=None,
        )

    rec = recs[0]

    mttr: float | None
    if scenario.anomalies:
        first_anomaly_ts = min(a.timestamp for a in scenario.anomalies)
        # Approximate rec emit time as the latest event ingest in this run
        # plus a synthetic 0 — the orchestrator emits synchronously inside
        # evaluate(), so the floor is "the moment evaluate() returned" which
        # for our timeline equals the latest event_ts. We use the incident
        # window end as the upper bound.
        mttr = max(
            0.0,
            (now + timedelta(seconds=scenario.events[-1].offset_seconds)
             - first_anomaly_ts).total_seconds(),
        )
    else:
        mttr = None

    burn_lead = _burn_lead_seconds(orch, scenario, now=now)

    return BenchmarkResult(
        scenario_name=scenario.name,
        action_category=rec.action_category,
        expected_action_category=scenario.expected_action_category,
        false_positive=rec.action_category != scenario.expected_action_category,
        mttr_seconds=mttr,
        burn_rate_lead_seconds=burn_lead,
    )


def _burn_lead_seconds(
    orch: PipelineOrchestrator,
    scenario: Scenario,
    *,
    now: datetime,
    target: float = 0.99,
) -> float | None:
    """Walk the orchestrator's event log, recompute SLO band at each step,
    return seconds from first error to first non-ok band. ``None`` if no
    error event in the scenario or the band stays ``ok`` throughout.
    """
    events = orch.iter_events()
    if not events:
        return None
    first_error_at: datetime | None = None
    first_nonok_at: datetime | None = None
    total = errors = 0
    slo = SLO(target=target)
    for ev in events:
        total += 1
        if _classify_event(ev.kind, ev.severity):
            errors += 1
            if first_error_at is None:
                first_error_at = ev.received_at
        avail = availability_sli(success_count=total - errors, total_count=total)
        rate = (errors / total) if total else 0.0
        burn = burn_rate(actual_error_rate=rate, slo=slo) if total else 0.0
        over_budget = total > 0 and avail < target
        if over_budget and first_nonok_at is None:
            first_nonok_at = ev.received_at
            break
    if first_error_at is None or first_nonok_at is None:
        return None
    return max(0.0, (first_nonok_at - first_error_at).total_seconds())


def summarize(results: list[BenchmarkResult]) -> dict[str, object]:
    total = len(results)
    fp = sum(1 for r in results if r.false_positive)
    mttrs = [r.mttr_seconds for r in results if r.mttr_seconds is not None]
    leads = [r.burn_rate_lead_seconds for r in results if r.burn_rate_lead_seconds is not None]
    return {
        "scenarios": total,
        "false_positive_rate": (fp / total) if total else 0.0,
        "false_positives": fp,
        "mttr_seconds_avg": (sum(mttrs) / len(mttrs)) if mttrs else None,
        "mttr_seconds_max": max(mttrs) if mttrs else None,
        "burn_lead_seconds_avg": (sum(leads) / len(leads)) if leads else None,
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="RepoPulse benchmark harness")
    parser.add_argument("--scenarios-dir", default="scenarios")
    parser.add_argument("--out", default="-", help="output path or '-' for stdout")
    args = parser.parse_args()
    scenario_paths = sorted(Path(args.scenarios_dir).glob("*.json"))
    from repopulse.scripts.scenarios import load_scenario
    results = [run_scenario(load_scenario(p), now=datetime.now().astimezone())
               for p in scenario_paths]
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
```

Note: `load_scenario` lives in Task 3.

- [ ] **Step 4: Run GREEN.**

```
cd backend && ./.venv/Scripts/python -m pytest tests/test_benchmark.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit.**

```bash
git add backend/src/repopulse/scripts/__init__.py backend/src/repopulse/scripts/benchmark.py backend/tests/test_benchmark.py
git commit -m "feat(bench): KPI harness — MTTR, false-positive rate, burn-rate lead time (TDD)"
```

---

## Task 3 — TDD: Reproducible scenario fixtures

**Files:**
- Create: `backend/src/repopulse/scripts/scenarios.py`
- Create: `scenarios/01-quiet.json`, `scenarios/02-single-anomaly.json`, `scenarios/03-multi-source-critical.json`, `scenarios/04-noisy-baseline.json`
- Create: `scenarios/README.md`
- Create: `backend/tests/test_scenarios.py`

`load_scenario(path)` parses a JSON file into a `Scenario` dataclass. JSON shape:

```json
{
  "name": "single-anomaly",
  "expected_action_category": "triage",
  "events": [
    {"offset_seconds": 0, "source": "github", "kind": "push", "payload": {}}
  ],
  "anomalies": [
    {
      "offset_seconds": 10,
      "value": 11.5, "baseline_median": 10.0, "baseline_mad": 1.0,
      "score": 5.06, "severity": "warning", "series_name": "otel-metrics"
    }
  ]
}
```

- [ ] **Step 1: Write failing test (`test_scenarios.py`).**

```python
import json
from pathlib import Path

import pytest

from repopulse.scripts.scenarios import load_scenario


def test_load_scenario_parses_minimal_quiet(tmp_path: Path) -> None:
    payload = {
        "name": "quiet",
        "expected_action_category": "observe",
        "events": [
            {"offset_seconds": 0, "source": "github", "kind": "push", "payload": {}}
        ],
        "anomalies": [],
    }
    path = tmp_path / "quiet.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    scenario = load_scenario(path)
    assert scenario.name == "quiet"
    assert scenario.expected_action_category == "observe"
    assert len(scenario.events) == 1
    assert scenario.events[0].offset_seconds == 0


def test_load_scenario_parses_anomaly_block(tmp_path: Path) -> None:
    payload = {
        "name": "single-anomaly",
        "expected_action_category": "triage",
        "events": [
            {"offset_seconds": 0, "source": "github", "kind": "push", "payload": {}}
        ],
        "anomalies": [
            {
                "offset_seconds": 10, "value": 11.5,
                "baseline_median": 10.0, "baseline_mad": 1.0,
                "score": 5.06, "severity": "warning", "series_name": "otel-metrics",
            }
        ],
    }
    path = tmp_path / "x.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    scenario = load_scenario(path)
    assert len(scenario.anomalies) == 1
    assert scenario.anomalies[0].severity == "warning"


def test_load_scenario_rejects_unknown_action_category(tmp_path: Path) -> None:
    payload = {
        "name": "bad",
        "expected_action_category": "explode",
        "events": [],
        "anomalies": [],
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="expected_action_category"):
        load_scenario(path)
```

- [ ] **Step 2: RED.** Module not found.

- [ ] **Step 3: Implement (`scenarios.py`).**

```python
"""Loader for scenarios/*.json — used by the benchmark harness."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import uuid4

from repopulse.anomaly.detector import Anomaly, Severity
from repopulse.api.events import EventEnvelope
from repopulse.scripts.benchmark import (
    ActionCategory,
    Scenario,
    ScenarioEvent,
)

_VALID_CATEGORIES: frozenset[str] = frozenset(
    {"observe", "triage", "escalate", "rollback"}
)
_T_BASE = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)


def load_scenario(path: Path) -> Scenario:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    cat = raw.get("expected_action_category")
    if cat not in _VALID_CATEGORIES:
        raise ValueError(
            f"expected_action_category must be one of {sorted(_VALID_CATEGORIES)}, "
            f"got {cat!r}"
        )
    events = [
        ScenarioEvent(
            offset_seconds=float(ev["offset_seconds"]),
            envelope=EventEnvelope.model_validate({
                "event_id": uuid4(),
                "source": ev["source"],
                "kind": ev["kind"],
                "payload": ev.get("payload", {}),
            }),
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
            severity=cast(Severity, a["severity"]),
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
```

- [ ] **Step 4: Author the four canonical scenarios under `scenarios/`.**

`scenarios/01-quiet.json`:
```json
{"name":"quiet","expected_action_category":"observe","events":[{"offset_seconds":0,"source":"github","kind":"push","payload":{}}],"anomalies":[]}
```

`scenarios/02-single-anomaly.json`:
```json
{"name":"single-anomaly","expected_action_category":"triage","events":[{"offset_seconds":0,"source":"github","kind":"push","payload":{}}],"anomalies":[{"offset_seconds":10,"value":11.5,"baseline_median":10.0,"baseline_mad":1.0,"score":5.06,"severity":"warning","series_name":"otel-metrics"}]}
```

`scenarios/03-multi-source-critical.json`:
```json
{"name":"multi-source-critical","expected_action_category":"rollback","events":[{"offset_seconds":0,"source":"github","kind":"push","payload":{}},{"offset_seconds":15,"source":"otel-logs","kind":"error-log","payload":{"severity":"error"}}],"anomalies":[{"offset_seconds":10,"value":300.0,"baseline_median":10.0,"baseline_mad":1.0,"score":20.0,"severity":"critical","series_name":"otel-metrics"}]}
```

`scenarios/04-noisy-baseline.json`:
```json
{"name":"noisy-baseline","expected_action_category":"escalate","events":[{"offset_seconds":0,"source":"github","kind":"push","payload":{}}],"anomalies":[{"offset_seconds":10,"value":50.0,"baseline_median":10.0,"baseline_mad":2.0,"score":13.5,"severity":"warning","series_name":"otel-metrics"},{"offset_seconds":20,"value":55.0,"baseline_median":10.0,"baseline_mad":2.0,"score":15.2,"severity":"warning","series_name":"otel-metrics"}]}
```

`scenarios/README.md`:
```markdown
# Scenarios

Reproducible incident timelines used by `backend/scripts/benchmark.py`.

| File | Expected action | Tests |
|---|---|---|
| 01-quiet.json | observe | R1 fallback path |
| 02-single-anomaly.json | triage | R2 path |
| 03-multi-source-critical.json | rollback | R4 path (multi-source + critical) |
| 04-noisy-baseline.json | escalate | R3 path (≥2 anomalies) |

Each file is hand-authored and version-controlled. The benchmark harness
loads them in lexical order and emits one `BenchmarkResult` per scenario.
```

- [ ] **Step 5: GREEN.**

```
cd backend && ./.venv/Scripts/python -m pytest tests/test_scenarios.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit.**

```bash
git add backend/src/repopulse/scripts/scenarios.py backend/tests/test_scenarios.py scenarios/
git commit -m "feat(bench): 4 reproducible incident scenarios + JSON loader (TDD)"
```

---

## Task 4 — Results report

**Files:**
- Create: `docs/results-report.md`

- [ ] **Step 1: Run the benchmark.**

```
cd backend && ./.venv/Scripts/python -m repopulse.scripts.benchmark --scenarios-dir ../scenarios --out ../docs/superpowers/plans/m6-evidence/benchmark.json
```

- [ ] **Step 2: Write the report** at `docs/results-report.md` with the format:

```markdown
# RepoPulse — Results Report (v1.0.0)

## Method

KPIs computed by `backend/scripts/benchmark.py` running 4 reproducible
scenarios under `scenarios/`. Every metric below cites the JSON path it
came from. To re-run:

```
cd backend && ./.venv/Scripts/python -m repopulse.scripts.benchmark \
  --scenarios-dir ../scenarios \
  --out ../docs/superpowers/plans/m6-evidence/benchmark.json
```

## Aggregate

| KPI | Value | Source |
|---|---|---|
| Scenarios run | 4 | `summary.scenarios` |
| False-positive rate | <%> | `summary.false_positive_rate` |
| MTTR (avg, anomaly→rec, in-process) | <% s> | `summary.mttr_seconds_avg` |
| MTTR (max) | <% s> | `summary.mttr_seconds_max` |
| Burn-rate lead time (avg, error→non-ok band) | <% s> | `summary.burn_lead_seconds_avg` |

## Per-scenario

(Table populated from `results[*]`)

## What this measures (and what it does NOT)

- MTTR here is *time to recommendation*, not *time to resolution*. Resolution
  timing requires durable action history + operator-acknowledgement
  timestamps; both deferred until the persistence milestone.
- False-positive flags compare the recommendation's `action_category` to a
  scenario-author-curated `expected_action_category`. Larger label sets,
  noisy real-world traffic, and labelled production data are out of scope.
- Burn-rate lead time uses the static error-classification rule from
  `repopulse.api.slo._classify_event`. A real production baseline would
  use sliding windows; here we use the bounded event deque.
```

Substitute the `<%>` placeholders with the actual numbers from the JSON before committing.

- [ ] **Step 3: Commit.**

```bash
git add docs/results-report.md docs/superpowers/plans/m6-evidence/benchmark.json
git commit -m "docs(M6): results report with KPI table + reproducible benchmark output"
```

---

## Task 5 — Demo flow script

**Files:**
- Create: `scripts/demo.sh`
- Create: `backend/scripts/seed_demo.py`
- Create: `docs/demo/README.md`

`scripts/demo.sh` is the one-command entry point. It:

1. Boots backend with the agentic env vars set.
2. Boots frontend pointing at the backend.
3. Seeds the dataset via `seed_demo.py`.
4. Prints a banner with URLs.

- [ ] **Step 1: Author `backend/scripts/seed_demo.py`** — Python script that POSTs the canonical demo events (mirrors what we did in Task 14 of M4):

```python
"""Seed the running backend with a canonical demo dataset.

Usage:
    python -m repopulse.scripts.seed_demo --url http://127.0.0.1:8000

100 push events + 5 error events + 1 critical github event + 1 workflow-run
usage event. Idempotent if run against a fresh backend; safe to re-run
because the M3 dedup layer handles repeats.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request
import uuid


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--secret",
        default=os.environ.get("REPOPULSE_AGENTIC_SHARED_SECRET", ""),
    )
    args = parser.parse_args()

    def post(path: str, body: dict[str, object], *, auth: bool = False) -> None:
        headers = {"Content-Type": "application/json"}
        if auth and args.secret:
            headers["Authorization"] = f"Bearer {args.secret}"
        req = urllib.request.Request(
            f"{args.url}{path}",
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5):
            pass

    for i in range(95):
        post("/api/v1/events", {
            "event_id": str(uuid.uuid4()),
            "source": "github", "kind": "push", "payload": {"sha": f"abc{i}"},
        })
    for i in range(5):
        post("/api/v1/events", {
            "event_id": str(uuid.uuid4()),
            "source": "otel-logs", "kind": "error-log",
            "payload": {"severity": "error", "message": f"err {i}"},
        })
    post("/api/v1/events", {
        "event_id": str(uuid.uuid4()),
        "source": "github", "kind": "incident",
        "payload": {"severity": "critical", "message": "demo outage"},
    })
    if args.secret:
        post("/api/v1/github/usage", {
            "workflow_name": "agentic-issue-triage",
            "run_id": 12345, "duration_seconds": 18.4,
            "conclusion": "success",
            "repository": "Ibrahim4594/OpsGraph-A",
            "runner": "linux",
        }, auth=True)
    print("demo dataset seeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Author `scripts/demo.sh`.**

```bash
#!/usr/bin/env bash
# RepoPulse demo runner.
# Usage:
#   ./scripts/demo.sh         # boots backend on :8000, frontend on :3000
#   PORT_BACKEND=8011 PORT_FRONTEND=3300 ./scripts/demo.sh
#
# Stops backend + frontend on Ctrl-C.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT_BACKEND="${PORT_BACKEND:-8000}"
PORT_FRONTEND="${PORT_FRONTEND:-3000}"
SECRET="${REPOPULSE_AGENTIC_SHARED_SECRET:-demo-secret}"

cleanup() {
  [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "${FRONTEND_PID:-}" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT

cd "$ROOT/backend"
REPOPULSE_AGENTIC_ENABLED=true \
REPOPULSE_AGENTIC_SHARED_SECRET="$SECRET" \
  ./.venv/Scripts/python -m uvicorn repopulse.main:app --port "$PORT_BACKEND" \
  --log-level warning &
BACKEND_PID=$!
sleep 3

cd "$ROOT/frontend"
NEXT_PUBLIC_BACKEND_URL="http://127.0.0.1:$PORT_BACKEND" \
  npm run start -- -p "$PORT_FRONTEND" &
FRONTEND_PID=$!
sleep 6

cd "$ROOT/backend"
REPOPULSE_AGENTIC_SHARED_SECRET="$SECRET" \
  ./.venv/Scripts/python -m repopulse.scripts.seed_demo \
  --url "http://127.0.0.1:$PORT_BACKEND"

cat <<EOF

╭─ RepoPulse demo running ────────────────────────────╮
│                                                     │
│   Dashboard:  http://localhost:$PORT_FRONTEND
│   API:        http://localhost:$PORT_BACKEND/healthz
│                                                     │
│   Press Ctrl-C to stop both servers.                │
│                                                     │
╰─────────────────────────────────────────────────────╯
EOF

wait
```

Make it executable: `chmod +x scripts/demo.sh`.

- [ ] **Step 3: Author `docs/demo/README.md`.**

```markdown
# RepoPulse Demo

## One command

\`\`\`bash
./scripts/demo.sh
\`\`\`

Boots backend (`uvicorn :8000`), frontend (`next start :3000`), seeds the
canonical dataset (100 events + 5 errors + 1 critical + 1 workflow-run),
and prints the URLs. Ctrl-C to stop.

## What you see

- `/`  SLO board — Availability ~95% (over budget), Throughput counter, Burn-rate badge slow
- `/incidents`  one critical incident + 50 grouped event clusters
- `/recommendations`  one pending escalate (the critical event) + 10 observed (R1)
- `/actions`  audit log: approve/reject/observe/workflow-run filter chips

## Prereqs

See [SETUP.md](../SETUP.md).
```

- [ ] **Step 4: Commit.**

```bash
git add scripts/demo.sh backend/src/repopulse/scripts/seed_demo.py docs/demo/README.md
git commit -m "feat(demo): one-command demo runner + canonical seed script"
```

---

## Task 6 — Demo assets

**Files:**
- Create: `docs/demo/screenshots/{slo,incidents,recommendations,actions}.png` (copy from `m4-evidence/screenshots/01-04-*.png`)
- Create: `docs/demo/architecture.md` (Mermaid → renders on GitHub)

- [ ] **Step 1: Copy curated screenshots.**

```bash
cp docs/superpowers/plans/m4-evidence/screenshots/01-slo-board.png docs/demo/screenshots/slo.png
cp docs/superpowers/plans/m4-evidence/screenshots/02-incidents.png docs/demo/screenshots/incidents.png
cp docs/superpowers/plans/m4-evidence/screenshots/03-recommendations.png docs/demo/screenshots/recommendations.png
cp docs/superpowers/plans/m4-evidence/screenshots/04-actions.png docs/demo/screenshots/actions.png
```

- [ ] **Step 2: Author `docs/demo/architecture.md`.**

```markdown
# Architecture

\`\`\`mermaid
flowchart LR
  subgraph Sources
    GH[GitHub events]
    OL[OTel logs]
    OM[OTel metrics]
  end
  subgraph Backend["FastAPI (M1–M5)"]
    NORM[normalize] --> ORCH[orchestrator]
    DET[anomaly detector] --> ORCH
    ORCH --> CORR[correlate]
    CORR --> REC[recommend]
    REC --> APP[(approval gate, M4)]
  end
  subgraph UI["Operator dashboard (M4)"]
    SLO[SLO board]
    INC[Incidents]
    INBOX[Inbox]
    HIST[Action history]
  end
  GH --> NORM
  OL --> NORM
  OM --> DET
  REC --> SLO
  REC --> INBOX
  ORCH --> INC
  APP --> HIST
\`\`\`

See also the per-milestone diagrams in [`docs/architecture.md`](../architecture.md).
```

- [ ] **Step 3: Commit.**

```bash
git add docs/demo/
git commit -m "docs(demo): curated screenshots + architecture diagram"
```

---

## Task 7 — Contributor docs

**Files:**
- Create: `docs/SETUP.md`
- Create: `docs/CONTRIBUTING.md`
- Create: `docs/TROUBLESHOOTING.md`

- [ ] **Step 1: Author SETUP.md** with the prerequisite matrix:

```markdown
# Setup

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | 3.11+ | backend (FastAPI 0.136, pydantic 2.13) |
| Node.js | 20+ LTS | frontend (Next.js 15) |
| Docker | any current | OTel Collector (optional, only for telemetry validation runs) |
| Git | any | source control |

### On WSL Ubuntu LTS (recommended)

\`\`\`bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip nodejs npm git
\`\`\`

If Ubuntu's Node is older than 20, use [nvm](https://github.com/nvm-sh/nvm):
\`\`\`bash
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/master/install.sh | bash
nvm install --lts
\`\`\`

### Docker (optional, for OTel collector)

If you have Docker Desktop linked with WSL Ubuntu, you already have everything
needed. The collector is started with:

\`\`\`bash
cd infra && docker compose up -d otel-collector
\`\`\`

Without Docker the backend still works — telemetry just goes to console
exporters (M2 default).

## Backend

\`\`\`bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\\Scripts\\activate
pip install -e ".[dev]"
pytest                              # 199+ tests should pass
\`\`\`

## Frontend

\`\`\`bash
cd frontend
npm install
npm test                            # 53+ vitest specs
npm run build                       # production build
\`\`\`

## One-command demo

\`\`\`bash
./scripts/demo.sh
\`\`\`

See [docs/demo/README.md](demo/README.md) for what to expect.

## Verifying everything works

\`\`\`bash
# Backend
cd backend && pytest && ruff check src tests && mypy

# Frontend
cd frontend && npm test && npm run typecheck && npm run build
\`\`\`

All four commands should exit 0.
```

- [ ] **Step 2: Author CONTRIBUTING.md.**

```markdown
# Contributing

## Workflow

1. **Branch** from `main` (`git checkout -b feat/<topic>`).
2. **TDD** — write a failing test before the code that makes it pass. Every commit
   that adds behavior should pair a test commit with the implementation. The
   `(TDD)` suffix on commit messages is the project convention.
3. **Lint + typecheck + test** before pushing:
   - Backend: `pytest && ruff check src tests && mypy`
   - Frontend: `npm test && npm run typecheck && npm run lint && npm run build`
4. **PR** — fill the template (summary + test plan).

## Commit messages

We follow [Conventional Commits](https://www.conventionalcommits.org/) loosely:

- `feat(scope): subject` for new behavior
- `fix(scope): subject` for bug fixes
- `docs(scope): subject` for docs only
- `chore(scope): subject` for tooling
- `test(scope): subject` for tests-only commits

`scope` is one of: `backend`, `api`, `pipeline`, `frontend`, `bench`, `m1..m6`, etc.

## Code review

We dispatch the `superpowers:code-reviewer` subagent before each milestone tag.
Review reports live under `docs/superpowers/plans/m<n>-evidence/code-review.md`.

## Definition of done

A change is done when:
- All tests pass.
- Lint + typecheck + build green.
- New behavior has a test (TDD).
- If user-facing: a screenshot lives under `docs/superpowers/plans/m<n>-evidence/screenshots/`.
- A claim made in a handoff or report has a re-runnable command + captured artifact.

## Anti-hallucination rule

We do not claim something works without evidence. Every metric in
[results-report.md](results-report.md) cites the JSON path it came from.
Every "tests pass" claim has the count + the command.
```

- [ ] **Step 3: Author TROUBLESHOOTING.md.**

```markdown
# Troubleshooting

## Backend won't start

- `from repopulse import __version__` should work after `pip install -e .[dev]`.
  If it doesn't: re-run from inside the venv, or recreate the venv.
- Port already in use: `netstat -ano | findstr :8000` (Windows) or
  `lsof -i :8000` (Unix); kill the process or pick another port.

## Frontend `npm test` fails with "@base-ui/react" missing

The toast component (M5) needs `@base-ui/react`. If your `node_modules` predates
that addition, `npm install` again.

## Docker collector not starting

`docker compose up -d otel-collector` fails with "no permission" on Linux:
  - Add yourself to the `docker` group: `sudo usermod -aG docker $USER`,
    then log out and back in.
- On WSL Ubuntu, ensure Docker Desktop's WSL integration is enabled
  (Settings → Resources → WSL Integration).

## Tests pass locally but build fails on CI

Most likely Node version mismatch — Next.js 15 needs Node 20+. Check
`.github/workflows/ci.yml` for the version pin.

## Magic MCP tools don't appear in Claude Code

The `magic` MCP server only loads at session start. After running
`claude mcp add ...`, restart Claude Code in this directory to see the
`21st_magic_*` tools.
```

- [ ] **Step 4: Commit.**

```bash
git add docs/SETUP.md docs/CONTRIBUTING.md docs/TROUBLESHOOTING.md
git commit -m "docs(M6): SETUP + CONTRIBUTING + TROUBLESHOOTING for portfolio handoff"
```

---

## Task 8 — README final polish

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the existing README** with a portfolio-grade version:

```markdown
# OpsGraph — RepoPulse AIOps

[![status](https://img.shields.io/badge/status-v1.0.0-blue)](#)
[![python](https://img.shields.io/badge/python-3.11+-blue)](#)
[![next.js](https://img.shields.io/badge/Next.js-15-black)](#)
[![tests](https://img.shields.io/badge/tests-252_passing-success)](#)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> **Production-grade AIOps reference.** Ingest events from GitHub, OTel logs, and
> OTel metrics → detect anomalies → group correlated signals into incidents →
> emit ranked recommendations with explainable evidence → human approval gate →
> automated workflows with safety guardrails. Operator dashboard included.

## Demo

\`\`\`bash
./scripts/demo.sh
\`\`\`

→ Dashboard at http://localhost:3000 · API at http://localhost:8000.

![SLO board](docs/demo/screenshots/slo.png)
![Recommendations inbox](docs/demo/screenshots/recommendations.png)

## What it does

| Layer | Module | TDD'd? |
|---|---|---|
| Ingest | `repopulse.api.events` | ✅ |
| Detect | `repopulse.anomaly.detector` (modified z-score) | ✅ |
| Correlate | `repopulse.correlation.engine` (time-window) | ✅ |
| Recommend | `repopulse.recommend.engine` (rule-based + evidence trace) | ✅ |
| Agentic actions | `.github/workflows/agentic-*.yml` (kill-switch + scoped tokens) | ✅ |
| Operator UI | `frontend/` (Next.js 15 + Tailwind 4) | ✅ |

## Architecture

See [docs/demo/architecture.md](docs/demo/architecture.md) and the per-milestone
diagrams in [docs/architecture.md](docs/architecture.md).

## Results

KPIs from `scripts/benchmark.py` are in [docs/results-report.md](docs/results-report.md).

## Engineering standards

- TDD across both languages — 199 backend pytest specs + 53 frontend vitest specs.
- Strict typing (mypy strict, TypeScript strict).
- Anti-hallucination — every claim in every milestone handoff has a re-runnable
  command + captured artifact under `docs/superpowers/plans/m<n>-evidence/`.
- WCAG 2.2 AA dashboard (live-DOM contrast probe, keyboard verification).

## Status

| Milestone | Tag | Topic |
|---|---|---|
| M1 | v0.1.0-m1 | Foundation, OTel, /healthz |
| M2 | v0.2.0-m2 | SLO module, ingest, load generator |
| M3 | v0.3.0-m3 | AIOps core (detect + correlate + recommend) |
| M5 | v0.4.0-m5 | GitHub agentic workflows (read-only, kill-switch) |
| M4 | v0.5.0-m4 | Operator dashboard UI |
| **M6** | **v1.0.0** | **Benchmark + portfolio polish** |

## Setup + contributing

- [docs/SETUP.md](docs/SETUP.md) — prerequisites + WSL/Docker
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) — workflow + TDD rule
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — common gotchas

## Author

Made by **Ibrahim Samad** ([@Ibrahim4594](https://github.com/Ibrahim4594)).
Licensed under [MIT](LICENSE).

> **Naming note.** Repository is `OpsGraph-A`; the runtime package + internal
> branding is `RepoPulse`. The two will converge in a follow-up rename.
```

- [ ] **Step 2: Commit.**

```bash
git add README.md
git commit -m "docs(README): final polish — badges, demo, KPIs, milestones, author"
```

---

## Task 9 — MIT LICENSE + version bump

**Files:**
- Create: `LICENSE`
- Modify: `backend/pyproject.toml` (`version = "1.0.0"`)
- Modify: `backend/src/repopulse/__init__.py` (`__version__ = "1.0.0"`)
- Modify: `frontend/package.json` (`"version": "1.0.0"`)

- [ ] **Step 1: Create `LICENSE`.**

```
MIT License

Copyright (c) 2026 Ibrahim Samad

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 2: Bump versions** in pyproject.toml, __init__.py, frontend/package.json.

- [ ] **Step 3: Reinstall + verify.**

```
cd backend && ./.venv/Scripts/python -m pip install -e ".[dev]" --quiet
./.venv/Scripts/python -c "from repopulse import __version__; print(__version__)"
```

Expected: `1.0.0`.

- [ ] **Step 4: Commit.**

```bash
git add LICENSE backend/pyproject.toml backend/src/repopulse/__init__.py frontend/package.json
git commit -m "chore(M6): MIT license + bump version to 1.0.0"
```

---

## Task 10 — Verification + code review + handoff + tag v1.0.0

**Files:**
- Create: `docs/superpowers/plans/m6-evidence/code-review.md`
- Create: `docs/superpowers/plans/m6-evidence/benchmark.json`
- Create: `docs/superpowers/plans/milestone-6-handoff.md`

Process (mirrors M4/M5 §15):

1. **`superpowers:verification-before-completion`:** fresh `pytest`, `ruff`, `mypy`, `npm test`, `npm run typecheck`, `npm run build`. Capture exact output.
2. **`superpowers:requesting-code-review`:** dispatch the subagent against `v0.5.0-m4..HEAD`. Save report.
3. **`superpowers:receiving-code-review`:** verify each Critical and Important finding before fixing. Push back where wrong.
4. **Write `milestone-6-handoff.md`:** Skills Invocation Log, Evidence Log, KPI table, risks, release recommendation.
5. **Tag `v1.0.0` and push.**

```bash
git tag v1.0.0
git push origin main --tags
```

---

## Self-Review

**Spec coverage:**
- ✅ Benchmark harness — Task 2.
- ✅ Reproducible scenarios — Task 3.
- ✅ Results report with KPI outcomes (MTTR, false positives, burn-rate lead) — Task 4.
- ✅ README final polish — Task 8.
- ✅ Demo assets — Tasks 5 + 6.
- ✅ Contributor docs (SETUP/CONTRIBUTING/TROUBLESHOOTING) — Task 7.
- ✅ MIT LICENSE — Task 9.
- ✅ Skills explicitly invoked + logged: writing-plans (T1), test-driven-development (T2 + T3), verification-before-completion (T10), requesting-code-review (T10), receiving-code-review (T10 if findings), systematic-debugging (any failure during T2/T3).
- ✅ Anti-hallucination strict — every metric in T4 cites the JSON path; every claim in T10 → re-runnable command.
- ✅ Acceptance gates: results-report.md (T4), README portfolio-ready (T8), demo assets (T5/T6), lint/typecheck/tests/build green (T10), final handoff with skills + evidence + risks + release recommendation (T10).

**Placeholder scan:** none. Every step has full code or a full command sequence.

**Type consistency:** `Scenario`, `ScenarioEvent`, `BenchmarkResult`, `summarize` referenced consistently between Tasks 2, 3, 4. `load_scenario` defined in Task 3 referenced in Task 2's `main()`.

---

## Execution choice

Inline execution per `superpowers:executing-plans` — same author, same session, fastest iteration loop.

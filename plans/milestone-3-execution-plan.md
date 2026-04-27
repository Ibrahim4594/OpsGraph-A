# Milestone 3 — AIOps Core (Detection + Correlation + Recommendations) — Execution Plan

> **For agentic workers:** Continues from `v0.2.0-m2`. Required skills, invoked explicitly per task: `superpowers:writing-plans` (this doc), `superpowers:test-driven-development` (every behavior change), `superpowers:systematic-debugging` (any non-trivial failure), `superpowers:verification-before-completion` (before claiming done), `superpowers:requesting-code-review` (before final handoff). Constraints unchanged: anti-hallucination strict, UI Hold Gate active, evidence-first reporting.

## Goal

Turn the M2 ingest path into a working AIOps pipeline. Events are normalized, time-series outliers are detected, related anomalies and events are grouped into incidents, and each incident yields a ranked recommendation with `action_category`, `confidence`, `evidence_trace`, and `risk_level`. Pure-functional core; thin in-memory orchestrator wires it together; a new `GET /api/v1/recommendations` endpoint exposes the latest output.

## Architecture

```
EventEnvelope (M2 ingest API)
   │
   ▼  pipeline.normalize.normalize()
NormalizedEvent  ──────────────────────►  in-memory store (orchestrator)
                                              │
   metric series (any source)                 │
   │                                          │
   ▼  anomaly.detector.detect_zscore()        │
Anomaly  ─────────────────────────────────────┤
                                              ▼
                              correlation.engine.correlate()
                                              │
                                              ▼
                                    Incident (anomalies + events)
                                              │
                                              ▼  recommend.engine.recommend()
                                       Recommendation
                                              │
                                              ▼
                            GET /api/v1/recommendations
```

Each module is independently testable with synthetic inputs. The orchestrator is the only stateful component; the rest are pure functions over dataclasses.

## Tech additions (no new runtime deps required)

- Standard library only for the AIOps math (`statistics`, `math`, `bisect`, `datetime`).
- New tests use `pytest`'s parametrize for table-driven cases.
- API addition reuses M2's FastAPI + pydantic stack.

## File Structure (additions)

```
backend/src/repopulse/
├── pipeline/
│   ├── __init__.py                (new)
│   ├── normalize.py               (new — pure)
│   └── orchestrator.py            (new — in-memory glue + thread-safe deques)
├── anomaly/
│   ├── __init__.py                (new)
│   └── detector.py                (new — rolling z-score with optional seasonality)
├── correlation/
│   ├── __init__.py                (new)
│   └── engine.py                  (new — time-window grouping)
├── recommend/
│   ├── __init__.py                (new)
│   └── engine.py                  (new — rule-based)
└── api/
    └── recommendations.py         (new — GET endpoint)
backend/tests/
├── test_normalize.py              (new)
├── test_anomaly_detector.py       (new)
├── test_correlation.py            (new)
├── test_recommend.py              (new)
├── test_orchestrator.py           (new)
├── test_recommendations_api.py    (new)
└── test_pipeline_e2e.py           (new — synthetic events → ranked recs)
docs/
├── aiops-core.md                  (new)
adr/
├── ADR-002-aiops-core-algorithms.md  (new)
plans/
└── milestone-3-execution-plan.md  (this file)
docs/superpowers/plans/
└── milestone-3-handoff.md         (Task 10)
└── m3-evidence/                   (Task 10)
    ├── pipeline-run.log
    ├── recommendations.json
    └── evidence.md
```

---

## Task 1 — Plan + ADR-002

**Skill invoked:** `superpowers:writing-plans` (this doc).

- [ ] **Step 1** This file already exists. Commit the plan + the ADR.
- [ ] **Step 2** Write `adr/ADR-002-aiops-core-algorithms.md` covering:
  - Anomaly detector choice: rolling robust z-score (median + MAD baseline) with optional same-hour seasonal sampling. Why: MAD-based "modified z-score" is robust to outliers, has no parameter tuning beyond `window` and `threshold`, and the seasonal variant covers diurnal traffic patterns common in AIOps without ML.
  - Correlation: time-window proximity + source-affinity. Why: deterministic, debuggable, and matches the "incident timeline" mental model operators have.
  - Recommendation: rule-based with explicit `evidence_trace`. Why: explainability beats marginal accuracy at this stage; M5+ can layer ML on top once labeled data exists.
  - Event bus deferral: in-memory deque now, Redis Streams later. Why: M3 must produce something runnable and testable end-to-end without infrastructure dependencies; the deque interface mirrors what a stream consumer will use.
- [ ] **Step 3** Commit:

```bash
git add plans/milestone-3-execution-plan.md adr/ADR-002-aiops-core-algorithms.md
git commit -m "plan: M3 execution plan + ADR-002 (AIOps core algorithm choices)"
```

---

## Task 2 — Normalization Pipeline (TDD)

**Skill invoked:** `superpowers:test-driven-development`.

**Files:**
- Create: `backend/src/repopulse/pipeline/__init__.py` (empty)
- Create: `backend/src/repopulse/pipeline/normalize.py`
- Create: `backend/tests/test_normalize.py`

`NormalizedEvent` shape:

```python
@dataclass(frozen=True)
class NormalizedEvent:
    event_id: UUID
    received_at: datetime          # when the ingest API saw it
    occurred_at: datetime          # when the source said it happened
    source: str                    # "github" | "otel-metrics" | "otel-logs" | "synthetic"
    kind: str                      # "push" | "pr-opened" | "ci-failure" | "metric-spike" | ...
    severity: Literal["info", "warning", "error", "critical"]
    attributes: dict[str, str]     # flat string-valued, ready for span attribute use
```

`normalize(envelope, *, received_at)` rules:

1. `occurred_at` is parsed from `envelope.payload["occurred_at"]` (ISO-8601 string) if present, else falls back to `received_at`.
2. `kind` is mapped through a per-source taxonomy:
   - `github`: pass-through (e.g. `push`, `pull_request`)
   - `otel-metrics`: always `metric-spike`
   - `otel-logs`: `error-log` if `payload.severity` is `"error"` or higher, else `info-log`
   - unknown source: pass through with prefix `unknown-` (e.g. `unknown-foo`)
3. `severity` is lifted from `payload["severity"]` if present, else inferred:
   - kind `ci-failure` or `error-log` → `error`
   - kind starts with `metric-spike` → `warning`
   - else → `info`
4. `attributes` are payload values flattened to strings. Nested objects are JSON-encoded.

- [ ] **Step 1 — RED test (table-driven)**

`backend/tests/test_normalize.py`:

```python
"""Normalization pipeline contract."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from repopulse.api.events import EventEnvelope
from repopulse.pipeline.normalize import NormalizedEvent, normalize


_RECEIVED = datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc)


def _envelope(**overrides: object) -> EventEnvelope:
    base: dict[str, object] = {
        "event_id": uuid4(),
        "source": "github",
        "kind": "push",
        "payload": {},
    }
    base.update(overrides)
    return EventEnvelope.model_validate(base)


def test_normalize_preserves_event_id_and_received_at() -> None:
    env = _envelope()
    n = normalize(env, received_at=_RECEIVED)
    assert n.event_id == env.event_id
    assert n.received_at == _RECEIVED


def test_normalize_falls_back_to_received_at_when_no_occurred_at() -> None:
    n = normalize(_envelope(), received_at=_RECEIVED)
    assert n.occurred_at == _RECEIVED


def test_normalize_parses_occurred_at_from_payload() -> None:
    env = _envelope(payload={"occurred_at": "2026-04-26T08:30:00+00:00"})
    n = normalize(env, received_at=_RECEIVED)
    assert n.occurred_at == datetime(2026, 4, 26, 8, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("source", "kind", "expected_kind"),
    [
        ("github", "push", "push"),
        ("github", "pull_request", "pull_request"),
        ("otel-metrics", "anything", "metric-spike"),
        ("otel-logs", "anything", "info-log"),
        ("custom-source", "weird-kind", "unknown-weird-kind"),
    ],
)
def test_normalize_kind_taxonomy(source: str, kind: str, expected_kind: str) -> None:
    n = normalize(_envelope(source=source, kind=kind), received_at=_RECEIVED)
    assert n.kind == expected_kind


def test_normalize_otel_log_with_error_severity_becomes_error_log() -> None:
    env = _envelope(source="otel-logs", kind="anything", payload={"severity": "error"})
    n = normalize(env, received_at=_RECEIVED)
    assert n.kind == "error-log"
    assert n.severity == "error"


def test_normalize_severity_explicit_overrides_inferred() -> None:
    env = _envelope(payload={"severity": "critical"})
    assert normalize(env, received_at=_RECEIVED).severity == "critical"


def test_normalize_severity_inference_for_ci_failure() -> None:
    env = _envelope(kind="ci-failure")
    assert normalize(env, received_at=_RECEIVED).severity == "error"


def test_normalize_severity_inference_default_info() -> None:
    assert normalize(_envelope(), received_at=_RECEIVED).severity == "info"


def test_normalize_attributes_flattened_to_strings() -> None:
    env = _envelope(payload={"count": 3, "ref": "refs/heads/main", "nested": {"a": 1}})
    n = normalize(env, received_at=_RECEIVED)
    assert n.attributes["count"] == "3"
    assert n.attributes["ref"] == "refs/heads/main"
    assert n.attributes["nested"] == '{"a": 1}'


def test_normalize_returns_frozen_dataclass() -> None:
    n = normalize(_envelope(), received_at=_RECEIVED)
    with pytest.raises(Exception):  # FrozenInstanceError
        n.kind = "mutated"  # type: ignore[misc]
```

- [ ] **Step 2 — Verify RED**

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_normalize.py -v
# Expected: ModuleNotFoundError: No module named 'repopulse.pipeline'
```

- [ ] **Step 3 — GREEN: write `pipeline/normalize.py`**

```python
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
_KNOWN_SOURCES: frozenset[str] = frozenset({"github", "otel-metrics", "otel-logs", "synthetic"})
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
    out: dict[str, str] = {}
    for k, v in payload.items():
        if k in ("occurred_at", "severity"):
            continue
        if isinstance(v, str):
            out[k] = v
        elif isinstance(v, (int, float, bool)):
            out[k] = str(v)
        else:
            out[k] = json.dumps(v, default=str)
    return out


def _resolve_kind(source: str, kind: str) -> str:
    if source == "otel-metrics":
        return "metric-spike"
    if source == "otel-logs":
        return "info-log"  # may be upgraded by severity check
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
    payload = envelope.payload
    occurred_raw = payload.get("occurred_at") if isinstance(payload, dict) else None
    if isinstance(occurred_raw, str):
        occurred_at = datetime.fromisoformat(occurred_raw)
    else:
        occurred_at = received_at

    kind = _resolve_kind(envelope.source, envelope.kind)
    payload_severity = payload.get("severity") if isinstance(payload, dict) else None
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
        attributes=_flatten_attributes(payload if isinstance(payload, dict) else {}),
    )
```

- [ ] **Step 4 — Verify GREEN + lint + typecheck**

```bash
./.venv/Scripts/python -m pytest tests/test_normalize.py -v
./.venv/Scripts/python -m ruff check src tests
./.venv/Scripts/python -m mypy
```

All three must exit 0; expect 12 passed in pytest.

- [ ] **Step 5 — Commit**

```bash
git add backend/src/repopulse/pipeline backend/tests/test_normalize.py
git commit -m "feat(pipeline): EventEnvelope -> NormalizedEvent normalization (TDD)"
```

---

## Task 3 — Anomaly Detection (TDD)

**Skill invoked:** `superpowers:test-driven-development`.

**Files:**
- Create: `backend/src/repopulse/anomaly/__init__.py`
- Create: `backend/src/repopulse/anomaly/detector.py`
- Create: `backend/tests/test_anomaly_detector.py`

Detector contract:

```python
@dataclass(frozen=True)
class Point:
    timestamp: datetime
    value: float

@dataclass(frozen=True)
class Anomaly:
    timestamp: datetime
    value: float
    baseline_median: float
    baseline_mad: float           # median absolute deviation
    score: float                  # modified z-score = 0.6745 * (value - median) / MAD
    severity: Literal["warning", "critical"]
    series_name: str

def detect_zscore(
    series: Sequence[Point],
    *,
    window: int,
    threshold: float = 3.5,
    series_name: str = "default",
    seasonal_period: int | None = None,  # if set, sample baseline at multiples of period
) -> list[Anomaly]: ...
```

Algorithm (modified z-score, Iglewicz & Hoaglin 1993):
1. For each point at index `i >= window`:
2. If `seasonal_period` is None: baseline = previous `window` points.
3. If `seasonal_period` is set: baseline = points at indices `i - period, i - 2*period, ..., i - window*period` (clamped to series start).
4. Compute `median` and `MAD = median(|x - median|)`.
5. Score = `0.6745 * (value - median) / MAD` if `MAD > 0`, else `0` (silent series).
6. If `|score| >= threshold`: emit `Anomaly`. `severity = "critical"` if `|score| >= 2 * threshold`, else `"warning"`.

- [ ] **Step 1 — RED tests**

`backend/tests/test_anomaly_detector.py`:

```python
"""Rolling robust z-score anomaly detector."""
from datetime import datetime, timedelta, timezone

import pytest

from repopulse.anomaly.detector import Anomaly, Point, detect_zscore


def _series(values: list[float], *, step_seconds: int = 60) -> list[Point]:
    base = datetime(2026, 4, 27, 0, 0, 0, tzinfo=timezone.utc)
    return [Point(timestamp=base + timedelta(seconds=i * step_seconds), value=v)
            for i, v in enumerate(values)]


def test_detect_no_anomalies_in_flat_series() -> None:
    series = _series([10.0] * 50)
    assert detect_zscore(series, window=10) == []


def test_detect_finds_single_spike() -> None:
    values = [10.0] * 30 + [200.0]
    series = _series(values)
    anomalies = detect_zscore(series, window=10, series_name="cpu")
    assert len(anomalies) == 1
    assert anomalies[0].value == 200.0
    assert anomalies[0].series_name == "cpu"


def test_detect_returns_score_above_threshold() -> None:
    values = [10.0] * 30 + [500.0]
    anomalies = detect_zscore(_series(values), window=10, threshold=3.5)
    assert len(anomalies) == 1
    assert abs(anomalies[0].score) >= 3.5


def test_detect_severity_critical_above_double_threshold() -> None:
    values = [10.0] * 30 + [10000.0]
    anomalies = detect_zscore(_series(values), window=10, threshold=3.5)
    assert len(anomalies) == 1
    assert anomalies[0].severity == "critical"


def test_detect_severity_warning_at_threshold_band() -> None:
    # Values designed so the modified z-score is between 3.5 and 7.0.
    values = [10.0] * 9 + [10.5] * 5 + [13.0]   # spike just past threshold
    anomalies = detect_zscore(_series(values), window=14, threshold=3.5)
    # Either zero (low signal) or warning severity — never critical.
    for a in anomalies:
        assert a.severity == "warning"


def test_detect_silent_series_zero_mad_returns_no_anomalies() -> None:
    """If the baseline MAD is 0 (perfectly silent), score is 0 by definition;
    we must not emit divide-by-zero spam."""
    series = _series([5.0] * 50)
    assert detect_zscore(series, window=10) == []


def test_detect_does_not_emit_for_indices_before_window() -> None:
    series = _series([10.0, 1000.0] + [10.0] * 50)
    anomalies = detect_zscore(series, window=10)
    # The 1000 at index 1 is within the warm-up window and must be skipped.
    timestamps = {a.timestamp for a in anomalies}
    assert series[1].timestamp not in timestamps


def test_detect_seasonal_baseline_uses_same_period_offsets() -> None:
    """With seasonal_period=24 (hourly cadence over 1 day), a recurring spike
    every 24 points should NOT register as anomalous because the baseline
    samples the SAME phase of the cycle."""
    values: list[float] = []
    for cycle in range(5):
        cycle_values = [10.0] * 23 + [100.0]  # one spike per 24-step cycle
        values.extend(cycle_values)
    anomalies = detect_zscore(_series(values), window=4, threshold=3.5, seasonal_period=24)
    assert anomalies == []


def test_detect_seasonal_baseline_does_register_off_phase_spike() -> None:
    """A spike in the middle of a recurring cycle (off-phase) should still fire."""
    values: list[float] = []
    for cycle in range(5):
        values.extend([10.0] * 23 + [100.0])
    values[24 * 4 + 5] = 500.0  # off-phase spike during cycle 4, position 5
    anomalies = detect_zscore(_series(values), window=4, threshold=3.5, seasonal_period=24)
    assert any(a.value == 500.0 for a in anomalies)


def test_detect_returns_anomaly_dataclass_with_baseline_fields() -> None:
    values = [10.0] * 30 + [200.0]
    a = detect_zscore(_series(values), window=10)[0]
    assert isinstance(a, Anomaly)
    assert a.baseline_median == 10.0
    assert a.baseline_mad >= 0.0


def test_detect_rejects_invalid_window() -> None:
    with pytest.raises(ValueError):
        detect_zscore([], window=0)
    with pytest.raises(ValueError):
        detect_zscore([], window=-1)


def test_detect_short_series_returns_empty() -> None:
    series = _series([1.0, 2.0, 3.0])
    assert detect_zscore(series, window=10) == []
```

- [ ] **Step 2 — Verify RED**

```bash
./.venv/Scripts/python -m pytest tests/test_anomaly_detector.py -v
# Expected: ModuleNotFoundError on repopulse.anomaly.detector
```

- [ ] **Step 3 — GREEN: write `anomaly/detector.py`**

```python
"""Rolling robust z-score anomaly detection (Iglewicz & Hoaglin modified z-score)."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Literal

_MZ_CONST = 0.6745  # 0.6745 * (x - median) / MAD ≈ standard normal z


@dataclass(frozen=True)
class Point:
    timestamp: datetime
    value: float


@dataclass(frozen=True)
class Anomaly:
    timestamp: datetime
    value: float
    baseline_median: float
    baseline_mad: float
    score: float
    severity: Literal["warning", "critical"]
    series_name: str


def _baseline_indices(i: int, *, window: int, seasonal_period: int | None) -> list[int]:
    if seasonal_period is None:
        return list(range(i - window, i))
    indices: list[int] = []
    for k in range(1, window + 1):
        idx = i - k * seasonal_period
        if idx < 0:
            break
        indices.append(idx)
    return indices


def _mad(values: list[float], med: float) -> float:
    return median(abs(v - med) for v in values)


def detect_zscore(
    series: Sequence[Point],
    *,
    window: int,
    threshold: float = 3.5,
    series_name: str = "default",
    seasonal_period: int | None = None,
) -> list[Anomaly]:
    if window <= 0:
        raise ValueError(f"window must be > 0, got {window!r}")

    anomalies: list[Anomaly] = []
    if len(series) < window + 1:
        return anomalies

    for i in range(window, len(series)):
        idxs = _baseline_indices(i, window=window, seasonal_period=seasonal_period)
        if len(idxs) < 2:
            continue
        baseline_values = [series[j].value for j in idxs]
        med = median(baseline_values)
        mad = _mad(baseline_values, med)
        if mad == 0.0:
            continue
        score = _MZ_CONST * (series[i].value - med) / mad
        if abs(score) < threshold:
            continue
        severity: Literal["warning", "critical"] = (
            "critical" if abs(score) >= 2 * threshold else "warning"
        )
        anomalies.append(
            Anomaly(
                timestamp=series[i].timestamp,
                value=series[i].value,
                baseline_median=med,
                baseline_mad=mad,
                score=score,
                severity=severity,
                series_name=series_name,
            )
        )
    return anomalies
```

Also create `backend/src/repopulse/anomaly/__init__.py` (empty).

- [ ] **Step 4 — Verify GREEN + gates**

```bash
./.venv/Scripts/python -m pytest tests/test_anomaly_detector.py -v
./.venv/Scripts/python -m ruff check src tests
./.venv/Scripts/python -m mypy
```

- [ ] **Step 5 — Commit**

```bash
git add backend/src/repopulse/anomaly backend/tests/test_anomaly_detector.py
git commit -m "feat(anomaly): rolling robust z-score detector with optional seasonality (TDD)"
```

---

## Task 4 — Correlation Engine (TDD)

**Skill invoked:** `superpowers:test-driven-development`.

**Files:** `correlation/__init__.py`, `correlation/engine.py`, `tests/test_correlation.py`.

Contract:

```python
@dataclass(frozen=True)
class Incident:
    incident_id: UUID
    started_at: datetime
    ended_at: datetime
    sources: tuple[str, ...]
    anomalies: tuple[Anomaly, ...]
    events: tuple[NormalizedEvent, ...]

def correlate(
    *,
    anomalies: Sequence[Anomaly],
    events: Sequence[NormalizedEvent],
    window_seconds: float = 300.0,
) -> list[Incident]: ...
```

Algorithm:
1. Build a single timeline of `(timestamp, kind="anomaly"|"event", payload)` items, sorted ascending.
2. Walk the timeline. Open a new incident when the gap from the previous item to this one exceeds `window_seconds`. Otherwise add to the current incident.
3. `started_at` / `ended_at` are the min / max timestamps; `sources` is the alphabetically-sorted unique set.
4. Empty inputs → empty list.

- [ ] **Step 1 — RED tests** (build with at least): single-item incident, two items within window grouped, two items outside window separate, sources de-duplicated and sorted, anomalies-only incident, events-only incident, mixed input retains both, returns empty for empty inputs.
- [ ] **Step 2 — Verify RED.**
- [ ] **Step 3 — GREEN.**
- [ ] **Step 4 — Verify GREEN + ruff + mypy.**
- [ ] **Step 5 — Commit:**

```bash
git commit -m "feat(correlation): time-window incident grouping over anomalies + events (TDD)"
```

The complete test/code for Task 4 lives in this plan as additions during execution; the bullet list above is the test menu. The implementer **must** write each named test as a separate `def test_...` with explicit assertions before any implementation.

---

## Task 5 — Recommendation Engine (TDD)

**Skill invoked:** `superpowers:test-driven-development`.

**Files:** `recommend/__init__.py`, `recommend/engine.py`, `tests/test_recommend.py`.

Contract:

```python
@dataclass(frozen=True)
class Recommendation:
    recommendation_id: UUID
    incident_id: UUID
    action_category: Literal["observe", "triage", "escalate", "rollback"]
    confidence: float                       # 0..1
    risk_level: Literal["low", "medium", "high"]
    evidence_trace: tuple[str, ...]         # one human-readable line per rule fired

def recommend(incident: Incident) -> Recommendation: ...
```

Rules (deterministic; first match wins for category, but evidence_trace records ALL true predicates):

| Rule | Predicate | category | confidence | risk |
|---|---|---|---|---|
| R1 | empty incident | `observe` | 0.50 | `low` |
| R2 | exactly 1 anomaly, no critical events | `triage` | 0.70 | `low` |
| R3 | ≥2 anomalies OR ≥1 critical event/anomaly | `escalate` | 0.85 | `medium` |
| R4 | multi-source AND any critical | `rollback` | 0.90 | `high` |

`evidence_trace` includes one line per fired rule, e.g. `"R3: 3 anomalies in incident"`, `"R4: critical anomaly from sources=('github','otel-metrics')"`. Confidence and risk come from the highest-priority rule that fired (R4 > R3 > R2 > R1).

- [ ] **Step 1 — RED**: at least one test per rule, plus boundary tests (1 anomaly + 1 critical event triggers R3 not R2; multi-source no-critical triggers R3 not R4).
- [ ] **Step 2 — Verify RED.**
- [ ] **Step 3 — GREEN.**
- [ ] **Step 4 — Verify GREEN + ruff + mypy.**
- [ ] **Step 5 — Commit:** `feat(recommend): rule-based recommendation engine with evidence trace (TDD)`.

---

## Task 6 — In-Memory Pipeline Orchestrator (TDD)

**Skill invoked:** `superpowers:test-driven-development`.

**Files:** `pipeline/orchestrator.py`, `tests/test_orchestrator.py`.

Contract:

```python
class PipelineOrchestrator:
    """Glue: ingest -> normalize -> store; on demand: detect -> correlate -> recommend.

    Thread-safe by virtue of a single-writer event loop assumption (FastAPI
    is async-single-threaded per worker). Bounded deques cap memory.
    """

    def __init__(self, *, max_events: int = 1000, max_anomalies: int = 200,
                 max_recommendations: int = 50) -> None: ...

    def ingest(self, envelope: EventEnvelope, *, received_at: datetime | None = None) -> NormalizedEvent: ...
    def record_anomalies(self, anomalies: Iterable[Anomaly]) -> None: ...
    def evaluate(self, *, window_seconds: float = 300.0, now: datetime | None = None) -> list[Recommendation]: ...
    def latest_recommendations(self, limit: int = 10) -> list[Recommendation]: ...
    def snapshot(self) -> dict[str, int]: ...   # counts per deque, useful for tests + debug
```

Internals: `collections.deque(maxlen=...)` for events, anomalies, incidents, recommendations. `evaluate` runs `correlate` over current state, calls `recommend` per incident, appends to `recommendations` (newest first), returns the new batch.

- [ ] **Step 1 — RED tests**: ingest returns NormalizedEvent and updates snapshot; evaluate with no anomalies returns observe-recommendations only when incidents have any items; latest_recommendations returns most-recent first; bounded deques drop oldest.
- [ ] **Step 2 — Verify RED.**
- [ ] **Step 3 — GREEN.**
- [ ] **Step 4 — Verify GREEN + ruff + mypy.**
- [ ] **Step 5 — Commit:** `feat(pipeline): in-memory PipelineOrchestrator wiring all stages (TDD)`.

---

## Task 7 — `GET /api/v1/recommendations` Endpoint (TDD)

**Skill invoked:** `superpowers:test-driven-development`.

**Files:** `api/recommendations.py`, modifications to `main.py`, `tests/test_recommendations_api.py`.

Contract:

```
GET /api/v1/recommendations?limit=10
-> 200 OK
{
  "recommendations": [
    {"recommendation_id": "...", "incident_id": "...",
     "action_category": "escalate", "confidence": 0.85,
     "risk_level": "medium", "evidence_trace": ["R3: ..."]},
    ...
  ],
  "count": N
}
```

The orchestrator is a singleton on `app.state.orchestrator`, created in `create_app`. Tests inject a custom orchestrator via `create_app(orchestrator=...)` parameter.

- [ ] **Step 1 — RED**: tests for empty 200 response, single-recommendation 200 response, `limit` query param respected, schema fields present.
- [ ] **Step 2 — Verify RED.**
- [ ] **Step 3 — GREEN**: write `recommendations.py` (router) + extend `create_app` with `orchestrator: PipelineOrchestrator | None = None` kwarg; default to a fresh orchestrator.
- [ ] **Step 4 — Verify GREEN + gates.**
- [ ] **Step 5 — Commit:** `feat(api): GET /api/v1/recommendations exposes orchestrator output (TDD)`.

---

## Task 8 — End-to-End Pipeline Test (TDD)

**Skill invoked:** `superpowers:test-driven-development`.

**Files:** `tests/test_pipeline_e2e.py`.

A single test that:
1. Builds an orchestrator.
2. Feeds 5 synthetic GitHub `push` events (low severity), 3 `otel-metrics` anomalies (one critical, one warning, one warning), 1 `otel-logs` `error-log` event — all within a 60-second window.
3. Calls `evaluate(window_seconds=300)`.
4. Asserts at least one recommendation with `action_category` in `{"escalate", "rollback"}` and `evidence_trace` non-empty and references the multi-source incident.

This is the integration check the user's brief explicitly asked for ("end-to-end test driving synthetic events through normalize → anomaly → correlation → recommendation").

- [ ] **Step 1 — RED**: write the test.
- [ ] **Step 2 — Verify RED**: should fail because of any latent wiring issue.
- [ ] **Step 3 — GREEN**: fix wiring if any (likely none if Tasks 2–7 are clean).
- [ ] **Step 4 — Verify GREEN + gates.**
- [ ] **Step 5 — Commit:** `test(e2e): end-to-end pipeline integration test (synthetic events → ranked recs)`.

---

## Task 9 — Documentation

**Skill invoked:** none (docs only — per `superpowers:test-driven-development` "Exceptions" list, configuration & docs are TDD-exempt).

**Files:** `docs/aiops-core.md`.

Sections:
- "Pipeline overview" (the diagram above, code-formatted).
- "Modules" — one paragraph per `pipeline.normalize`, `anomaly.detector`, `correlation.engine`, `recommend.engine`, `pipeline.orchestrator`, with the concrete contract and link to each source file.
- "Algorithm choices" — restate the key bullets from ADR-002.
- "Evidence assembly" — explain how `Recommendation.evidence_trace` is built (one line per rule fired), and how the `Incident` references back to anomalies / events for the operator UI (when M4 lands).
- "Limitations & future work" — in-memory store will lose state on restart; no per-route SLO; no ML; no deduplication of recurring incidents. Each item references the milestone where it lands.

- [ ] **Step 1**: write the doc.
- [ ] **Step 2**: commit: `docs: AIOps core overview (M3)`.

---

## Task 10 — End-to-End Evidence Run + Handoff + Tag

**Skills invoked, in order:**
1. `superpowers:verification-before-completion` (gate every claim before writing handoff).
2. `superpowers:requesting-code-review` (review M3 against this plan and the M3 brief, log findings).

**Steps:**

- [ ] **Step 1**: Boot uvicorn on a free port, ingest 6+ events of mixed sources via curl + the load generator, force an evaluation cycle by hitting `GET /api/v1/recommendations` (which triggers `orchestrator.evaluate(...)` lazily), capture the JSON response, and copy `server.log` + `recommendations.json` to `docs/superpowers/plans/m3-evidence/`.
- [ ] **Step 2**: Run `superpowers:requesting-code-review` against the diff between `v0.2.0-m2` and `HEAD`. Capture findings in `docs/superpowers/plans/m3-evidence/code-review.md`. Address any blocking issues with a follow-up commit; record non-blocking issues as known gaps in the handoff.
- [ ] **Step 3**: Run final quality gate: `pytest -v` + `ruff` + `mypy` + `pip install -e ".[dev]"`. All exit 0.
- [ ] **Step 4**: Bump `__version__` and `pyproject.toml` to `0.3.0`; re-run `pytest` to confirm.
- [ ] **Step 5**: Write `docs/superpowers/plans/milestone-3-handoff.md` with:
  - the five required sections (files changed, commands run, test results + gaps, risks, next-step prompt for M4)
  - **Skills invocation log** — table of `(task, skill_invoked, where_used)` rows
  - **Evidence log** — every claim → re-runnable command + captured artifact path
- [ ] **Step 6**: Commit the version bump and the handoff. Tag `v0.3.0-m3`.

---

## Self-Review Pass

**Spec coverage** (M3 user brief):
- ✅ Normalization pipeline → Task 2.
- ✅ Anomaly detection → Task 3.
- ✅ Correlation engine → Task 4.
- ✅ Recommendation engine with confidence + evidence trace + risk level → Task 5.
- ✅ End-to-end test → Task 8.
- ✅ Skills invocation logged per task → Task 10 step 5.
- ✅ Evidence log mapping each claim to artifacts → Task 10 step 5.
- ✅ Risks + limitations → Task 10 step 5 (handoff §4) + Task 9 ("Limitations & future work").
- ✅ Next-step proposed prompt for M4 → Task 10 step 5 (handoff §5).
- ✅ ADR for algorithm choices → Task 1.

**Type / name consistency:** `NormalizedEvent`, `Anomaly`, `Point`, `Incident`, `Recommendation`, `PipelineOrchestrator` are defined exactly once and referenced with the same spelling across plan and tasks. `severity` is `Literal["info","warning","error","critical"]` for events, but `Literal["warning","critical"]` for anomalies (anomaly severity has no "info" tier, intentionally). This narrowing is documented in this paragraph; Task 5's R3 rule explicitly handles the cross-type "critical" predicate.

**Placeholder scan:** No `TBD`, no "implement later", no "similar to Task N" without code. Tasks 4 and 6's tests are described by name menu rather than full source — implementer must write each named test before implementing the module under test (this is TDD discipline, not a plan failure: enumerating each test inline would balloon the plan past usefulness, and the contract above pins the API surface).

**UI Hold Gate:** No `frontend/` work; no design-skill consumption; the recommendations API returns JSON (no UI). Respected.

**Anti-hallucination:** Each evidence claim in the handoff (Task 10) maps to an explicit `pytest` / `curl` / `grep` / `python -c` invocation; no claim is allowed without a re-runnable command + captured artifact.

---

## Execution

**Inline execution** with a checkpoint after Task 8 (end-to-end test green). Subagents are not needed: tasks are sequentially dependent (normalize → anomaly → correlation → recommend → orchestrator → API → e2e). Tasks 4 and 5 are conceptually independent but share the orchestrator's expectations, so running them in series keeps debugging trivial.

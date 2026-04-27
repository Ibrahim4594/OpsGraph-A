# AIOps Core

The AIOps core is the M3 deliverable: events arriving at `/api/v1/events` are normalized, time-series spikes are detected, related signals are correlated into incidents, and each incident yields an explainable recommendation. The pieces compose end-to-end through an in-memory orchestrator and surface as JSON via `GET /api/v1/recommendations`. Algorithm choices are recorded in [`adr/ADR-002-aiops-core-algorithms.md`](../adr/ADR-002-aiops-core-algorithms.md).

## Pipeline Overview

```
EventEnvelope (POST /api/v1/events)
   │
   ▼  pipeline.normalize.normalize()
NormalizedEvent  ─────────────►  in-memory store (PipelineOrchestrator)
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

Each box is a pure function over dataclasses. The orchestrator is the only stateful component.

## Modules

### `pipeline.normalize` — [source](../backend/src/repopulse/pipeline/normalize.py)

Pure function `normalize(envelope, *, received_at) -> NormalizedEvent`. Maps the inbound `EventEnvelope` (M2) to a canonical event with explicit `received_at`, parsed `occurred_at`, source-aware `kind` taxonomy, and inferred `severity`. `attributes` are flattened to strings so the value can be reused as OTel span attributes.

### `anomaly.detector` — [source](../backend/src/repopulse/anomaly/detector.py)

`detect_zscore(series, *, window, threshold=3.5, series_name="default", seasonal_period=None) -> list[Anomaly]`. Modified z-score (Iglewicz & Hoaglin, 1993). When `MAD == 0` and the value differs from the median, emits a critical-severity anomaly with infinite score (the "perfectly silent baseline" case is the strongest possible signal, not the weakest). When `seasonal_period` is set, the baseline window samples the same phase of the cycle (e.g., the previous `window` same-hour-of-day points) instead of the contiguous prior points.

### `correlation.engine` — [source](../backend/src/repopulse/correlation/engine.py)

`correlate(*, anomalies, events, window_seconds=300.0) -> list[Incident]`. Merges anomalies and events into a single sorted timeline, walks once, and opens a new incident whenever the gap from the previous item exceeds `window_seconds`. `Incident.sources` is the alphabetically-sorted unique set of contributing sources, so multi-source incidents are first-class.

### `recommend.engine` — [source](../backend/src/repopulse/recommend/engine.py)

`recommend(incident) -> Recommendation`. Four rules in priority order:

| Rule | Predicate | Category | Confidence | Risk |
|---|---|---|---|---|
| R4 | `len(sources) ≥ 2` AND any critical | `rollback` | 0.90 | high |
| R3 | `≥ 2 anomalies` OR any critical | `escalate` | 0.85 | medium |
| R2 | exactly 1 anomaly, no critical | `triage` | 0.70 | low |
| R1 | empty incident | `observe` | 0.50 | low |

The highest-priority firing rule sets `action_category`, `confidence`, `risk_level`. Every firing rule contributes a one-line entry to `evidence_trace`, so an operator reading a recommendation can audit why each rule fired (or didn't).

### `pipeline.orchestrator` — [source](../backend/src/repopulse/pipeline/orchestrator.py)

`PipelineOrchestrator` owns four bounded `collections.deque` instances (events, anomalies, incidents, recommendations) with explicit `maxlen` caps. Methods:

- `ingest(envelope, *, received_at=None) -> NormalizedEvent`
- `record_anomalies(anomalies)`
- `evaluate(*, window_seconds=300.0) -> list[Recommendation]`
- `latest_recommendations(limit=10) -> list[Recommendation]`
- `snapshot() -> dict[str, int]`

The interface is intentionally Redis-Streams-shaped — swapping the deques for a real bus is a one-file change once persistence requirements arrive (see ADR-002 §"Event bus").

### `api.recommendations` — [source](../backend/src/repopulse/api/recommendations.py)

`GET /api/v1/recommendations?limit=10` returns the latest N recommendations (newest first). The endpoint is a pure read of the orchestrator's recommendation deque; it does **not** trigger evaluation. The pipeline is driven by ingest: every successful `POST /api/v1/events` (see [`api/events.py`](../backend/src/repopulse/api/events.py)) calls `orchestrator.ingest(...)` followed by `orchestrator.evaluate(...)`, so the GET endpoint reflects the latest state without an extra trigger call. Repeat ingests of identical content do not re-emit duplicate recommendations — `evaluate()` dedupes incidents by content signature.

Schema:

```json
{
  "recommendations": [
    {
      "recommendation_id": "uuid",
      "incident_id": "uuid",
      "action_category": "observe|triage|escalate|rollback",
      "confidence": 0.85,
      "risk_level": "low|medium|high",
      "evidence_trace": ["R3: ...", "R4: ..."]
    }
  ],
  "count": 1
}
```

## Algorithm Choices (summary; full rationale in ADR-002)

- **Detector** — modified z-score with MAD baseline. Robust to outliers in the baseline window. Optional seasonal-baseline sampling suppresses false positives on diurnal/weekly cycles.
- **Correlation** — time-window proximity over a unified timeline. Deterministic, debuggable, easy to explain to operators. Multi-source incidents fall out for free.
- **Recommendation** — rule-based with explicit evidence trace. Explainability beats marginal accuracy at this stage; M5+ can layer LLM reasoning on top of the deterministic output as structured input.

## Evidence Assembly

`Recommendation.evidence_trace` is constructed by evaluating every rule against the incident, regardless of priority, and collecting one explanation line per **fired** rule. The first line corresponds to the highest-priority firing rule (which also dictates `action_category`, `confidence`, and `risk_level`). For example, a multi-source critical incident produces:

```
"R4: multi-source (3) AND ≥1 critical → rollback (sources=['github','otel-logs','otel-metrics'], fired=True)"
"R3: ≥2 anomalies OR ≥1 critical → escalate (anomalies=2, any_critical=True, fired=True)"
```

The eventual operator UI will render this trace alongside the linked `Incident.anomalies` / `Incident.events` so a human can re-derive the agent's reasoning before approving any destructive action.

## Limitations & Future Work

- **In-memory state** — the orchestrator's deques live in process memory; a restart loses recent recommendations. Persistence + a real event bus land alongside Redis Streams in a future ADR (planned for M5 or sooner if scale demands).
- **Per-route SLO breakdown** — current SLOs are aggregated at the service level (see `docs/slo-spec.md`); per-route work waits until M3 has labeled traffic to justify the granularity.
- **No ML** — by design for M3. Once labeled incidents accrue, an ADR should evaluate ML-augmented detection / classification on top of the deterministic core.
- **No deduplication** — repeated incidents within a short window currently produce one recommendation each. A "merge similar recent incidents" step is straightforward to add and will appear when noise complaints justify it.
- **Single anomaly entry point** — `record_anomalies` is currently called manually (e.g. by the synthetic load generator or a test fixture); wiring `detect_zscore` into a periodic background task that polls a metrics source is the next obvious step and lands in M5 alongside the GitHub workflows.

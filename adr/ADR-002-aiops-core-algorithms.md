# ADR-002: AIOps Core Algorithm Choices

- **Status:** Accepted
- **Date:** 2026-04-27
- **Deciders:** Project owner (Ibrahim)
- **Supersedes:** —
- **Superseded by:** —

## Context

Milestone 3 must deliver a working AIOps pipeline (normalize → detect → correlate → recommend) with explainable outputs and reproducible behavior. The parent plan calls for a "robust baseline + seasonality-aware rules" detector, "correlation that groups related signals," and a "recommendation engine with action category, confidence, evidence trace, and risk level." We have no labeled data yet, no streaming infrastructure, and the operator UI is deferred to the very end of the project. We want fast feedback, reviewable code, and zero ML dependencies in M3.

## Decision

### Anomaly detector — modified z-score (Iglewicz & Hoaglin, 1993) with optional seasonal-baseline sampling

For each point at index `i ≥ window`, build a baseline window (either the previous `window` points, or the `window` points at multiples of `seasonal_period` strides back). Compute median `M` and median absolute deviation `MAD`. The modified z-score is `0.6745 × (xᵢ − M) / MAD`. Emit an `Anomaly` when `|score| ≥ threshold` (default 3.5, the standard recommendation in the literature). `severity = "critical"` when `|score| ≥ 2 × threshold`, else `"warning"`.

**Special case — `MAD = 0`:**

- If `xᵢ == M` (truly silent: baseline is flat, value matches baseline): emit nothing. There is no signal.
- If `xᵢ != M` (flat baseline followed by a deviation, e.g. an idle queue suddenly spiking): emit a `critical` anomaly with `score = ±inf`. A perfectly silent baseline followed by any deviation is the strongest possible signal, not the weakest. The original draft of this ADR said "emit nothing" for any `MAD = 0` case; that simplification was rejected during M3 implementation when the failing test `test_detect_finds_single_spike` (baseline `[10.0]*30`, value `200.0`) showed it would silently swallow real anomalies. See the M3 handoff "systematic-debugging" section for the trace.

### Correlation — time-window proximity over a unified anomaly+event timeline

Sort all anomalies and normalized events by timestamp into a single stream. Walk the stream; whenever the gap from the previous item exceeds `window_seconds` (default 300 s = 5 min), close the current incident and start a new one. Each `Incident` records its time bounds, the unique sources contributing, the anomalies, and the events. Multi-source incidents are first-class.

### Recommendation engine — rule-based with explicit evidence_trace

Four action categories: `observe`, `triage`, `escalate`, `rollback`, in increasing severity. Rules are deterministic and run in priority order; the highest-priority firing rule sets the category, confidence, and risk level. Every firing rule contributes a one-line entry to `evidence_trace`. There is no ML; there are no learned weights.

### Event "bus" — bounded `collections.deque` (in-process)

The orchestrator owns three deques (events, anomalies, recommendations) with explicit `maxlen` caps. The interface (`ingest`, `record_anomalies`, `evaluate`, `latest_recommendations`) matches what a Redis Streams consumer will expose later, so the swap is a one-file change.

## Alternatives Considered

1. **Classical statistical (mean ± k·σ).** Rejected: not robust to outliers, exactly the case AIOps needs to handle.
2. **EWMA + control charts.** Considered. Strong candidate; deferred because MAD is parameter-light and the seasonal-baseline trick is easier to explain in operator-facing docs. Add EWMA as an alternate detector in a future ADR if/when MAD's false-positive rate proves too high.
3. **Isolation Forest / Prophet / scikit-learn.** Rejected for M3: introduces training data, model lifecycle, and ML dependencies before the project has any labels. Reconsider in M5+ when labeled incidents accrue.
4. **Graph-based correlation (e.g. PageRank over service dependencies).** Rejected for M3: requires a service map we don't have. Time-window proximity is the canonical first cut.
5. **LLM-driven recommendation.** Rejected for M3: explainability and determinism beat marginal accuracy at this stage. M5's GitHub agentic workflows can layer LLM-flavored reasoning on top of the deterministic recommendation as a structured input.
6. **Redis Streams now.** Deferred: introduces a service to run, manage, and test against. The deque interface is intentionally Redis-Streams-shaped so the upgrade is local. Decision will be revisited in M5 when scale or durability demands it.

## Consequences

**Positive**
- Zero new runtime deps for the AIOps math (standard library only).
- Pure-functional core with parameter-light algorithms makes everything trivially testable.
- `evidence_trace` makes recommendations operator-debuggable from day one.
- Replacing the deque with a real bus is a single-file change because the interface is already drawn.

**Negative**
- MAD-based detection has well-known false-negative cases on multimodal distributions; we accept that for now.
- Time-window correlation will sometimes group unrelated incidents that happen to overlap. Manual triage will catch these; we will revisit when noise complaints arrive.
- In-memory store loses state on restart — operationally fine for M3 (we have no persistence requirement yet), bad for any production claim. Persistence lands when the bus does.

## Related ADRs

- **ADR-001** — establishes the hybrid backend/frontend split that this milestone slots into.
- **ADR-003 (planned, M3 follow-on or M5)** — event bus + persistence choice.
- **ADR-004 (planned, UI milestone)** — operator dashboard architecture.

# RepoPulse — Results Report (v1.0.0)

## Method

KPIs computed by `backend/scripts/benchmark.py` running 4 reproducible
scenarios under [`scenarios/`](../scenarios/). Every metric below cites
the JSON path it came from, so the value is verifiable by running the
same command and reading the same field — no hand-curated numbers.

### Re-run command

```bash
cd backend && ./.venv/Scripts/python -m repopulse.scripts.benchmark \
  --scenarios-dir ../scenarios \
  --out ../docs/superpowers/plans/m6-evidence/benchmark.json
```

(On Linux/macOS replace `./.venv/Scripts/python` with `./.venv/bin/python`.)

The harness:
1. Loads each `scenarios/*.json` via `repopulse.scripts.scenarios.load_scenario`.
2. Drives a fresh `PipelineOrchestrator` in-process — no HTTP, no clock skew.
3. Re-anchors anomaly timestamps to the runtime `now` so events and anomalies
   share the 300s correlation window (regression-tested, see
   `test_run_scenario_loaded_fixture_with_anomalies_does_not_observe`).
4. Calls `evaluate(window_seconds=300.0)` once, reads the latest
   `Recommendation`, computes per-scenario KPIs, and aggregates.

### KPI definitions (locked here)

- **MTTR** — *time-to-recommendation*. Seconds from the first anomaly's
  rebased timestamp to the latest of (last event arrival, last anomaly
  arrival), the earliest moment a streaming pipeline could emit the
  recommendation. Floors at 0. `null` when the scenario has no anomalies.
- **False-positive flag** — `True` iff the engine's
  `recommendation.action_category` differs from
  `scenario.expected_action_category`. The scenario author curates the
  expectation.
- **Burn-rate lead time** — seconds from the first error-classified event
  (`kind == "error-log"` or `severity ∈ {"error", "critical"}`) to the
  first SLO sample where `burn_band != "ok"`. Computed by walking the
  orchestrator's event log and replaying `availability_sli` + `burn_rate`
  per step. `null` if no error event in the scenario or the band stays ok.

## Aggregate KPIs

Source file: [`docs/superpowers/plans/m6-evidence/benchmark.json`](superpowers/plans/m6-evidence/benchmark.json).

| KPI | Value | JSON path |
|---|---|---|
| Scenarios run | **4** | `summary.scenarios` |
| False-positive rate | **0%** (0 / 4) | `summary.false_positive_rate` |
| MTTR (avg, anomaly→trigger) | **5.0 s** | `summary.mttr_seconds_avg` |
| MTTR (max) | **10.0 s** | `summary.mttr_seconds_max` |
| Burn-rate lead time (avg) | **0.0 s** | `summary.burn_lead_seconds_avg` |

## Per-scenario detail

| Scenario | Expected | Got | FP? | MTTR | Burn lead | Path |
|---|---|---|---|---|---|---|
| `quiet` | observe | observe | ✅ | n/a | n/a | `results[0]` |
| `single-anomaly` | triage | triage | ✅ | 0.0 s | n/a | `results[1]` |
| `multi-source-critical` | rollback | rollback | ✅ | 5.0 s | 0.0 s | `results[2]` |
| `noisy-baseline` | escalate | escalate | ✅ | 10.0 s | n/a | `results[3]` |

### Reading the per-scenario MTTRs

- **single-anomaly**: event at offset 0 s, anomaly at offset 10 s. The
  anomaly arrives *after* the event; max(last_event=0, last_anomaly=10) − first_anomaly=10 = **0 s**.
- **multi-source-critical**: event at 0 s, anomaly at 10 s, error-log event at 15 s.
  max(15, 10) − 10 = **5 s**.
- **noisy-baseline**: event at 0 s, anomalies at 10 s and 20 s.
  max(0, 20) − 10 = **10 s**.

### Reading the burn-rate lead

Only `multi-source-critical` includes an error-classified event. The 0 s
lead means the SLO availability dropped below the 0.99 default target on
that very first error event — expected, because the scenario has only
2 events total (1 push + 1 error) so 50% error rate ≈ availability 0.5
≪ 0.99 target.

## What this measures (and what it does NOT)

- **MTTR here is *time to recommendation*, not *time to resolution*.**
  Resolution timing requires durable action history with operator
  acknowledgement timestamps, both deferred until the persistence
  milestone.
- **False-positive flags compare against *author-curated* expected categories.**
  The four scenarios are deliberately archetypal (one per rule R1–R4)
  to verify the rule engine's correctness end-to-end. Larger label sets,
  noisy real-world traffic, or labelled production data are out of scope
  for this milestone.
- **Burn-rate lead time uses the static error-classification rule** from
  `repopulse.api.slo._classify_event`. A real production baseline would
  use sliding windows; here we use the bounded event deque.
- **All measurements are in-process and single-threaded.** Real network,
  real OTel ingest, and real concurrent-operator behavior are out of
  scope for the v1.0.0 portfolio release.

## Why these numbers are honest

1. The harness is TDD'd — see `backend/tests/test_benchmark.py`
   (8 specs) and `backend/tests/test_scenarios.py` (4 specs).
2. The fixtures are version-controlled markdown-adjacent JSON. Anyone can
   `git checkout v1.0.0` and re-run the benchmark to get the same values.
3. The metric definitions live in this document and in
   `backend/src/repopulse/scripts/benchmark.py` docstrings — both
   reviewed during the M6 code review.
4. There is no hand-curated number anywhere. Every value above maps to a
   field in `benchmark.json`.

## Next benchmarks (out of scope for v1.0.0)

- Real-world traffic replay against the OTel collector (M7+ — needs
  collector ingest persistence).
- Latency percentiles per pipeline stage (M7+ — needs in-process
  span instrumentation, partly already there via OTel SDK).
- Operator acknowledgement timing (M7+ — needs durable action history).
- Anomaly-detection accuracy on labelled production data (depends on
  acquiring such a dataset).

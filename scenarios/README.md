# Scenarios

Reproducible incident timelines used by `backend/scripts/benchmark.py`.

| File | Expected category | Tests path |
|---|---|---|
| `01-quiet.json` | observe | R1 fallback (no anomalies → benign event) |
| `02-single-anomaly.json` | triage | R2 (1 warning anomaly, no critical) |
| `03-multi-source-critical.json` | rollback | R4 (multi-source + critical anomaly) |
| `04-noisy-baseline.json` | escalate | R3 (≥2 anomalies, no critical) |

Each file is hand-authored and version-controlled. The benchmark harness
loads them in lexical order and emits one `BenchmarkResult` per scenario.

## Adding a scenario

1. Drop a new `NN-name.json` here following the existing shape.
2. Add the expected category — must be one of
   `observe | triage | escalate | rollback`.
3. Re-run the benchmark and the loader's `test_load_scenario_loads_canonical_fixtures`
   test (it counts files; bump the assertion if you add one).

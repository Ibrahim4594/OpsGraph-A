# M3 Evidence Run — 2026-04-27 (post-review)

This file documents the M3 acceptance evidence captured **after** the M3 code-review fixes (C1, C2, I1–I5) landed. The relevant commits are at the top of `git log` between `v0.2.0-m2` and `v0.3.0-m3`.

The pipeline is exercised two ways:

1. **HTTP-driven** — POST to `/api/v1/events`, GET `/api/v1/recommendations`. Proves the wiring fix from review C1.
2. **In-process** — drive the orchestrator directly with anomalies (the HTTP API does not yet expose `record_anomalies`; that lands when the metric-source ingest path goes in alongside the M5 GitHub workflows).

## Path 1 — HTTP-driven (C1 wiring + C2 idempotence)

Backend booted: `uvicorn repopulse.main:app --port 8006`. Captured stdout: `server.log` (~1950 lines of OTel JSON spans + uvicorn access logs).

### Step 1 — `/healthz`

```
{"status":"ok","service":"RepoPulse","environment":"development","version":"0.3.0"}
```

`service.version` reflects the M3 release (0.3.0) on every span.

### Step 2 — Empty recommendations (cold start)

```
GET /api/v1/recommendations
{"recommendations":[],"count":0}
```

Saved to `recommendations-empty.json`.

### Step 3 — POST 6 events (5 GitHub push + 1 otel-logs error)

After the round of 6 POSTs, GET returns **6 recommendations** (`recommendations-after-events.json`). Each ingest triggers `orchestrator.evaluate()` — so the deque grows by one event per POST, and each evaluation produces a fresh incident covering the deque-so-far. All 6 recommendations are `observe` (R1 fallback) because no anomalies have been recorded; this is the correct algorithmic output for the input given to the HTTP path.

The point of this path is the wiring: prior to the C1 fix, GET would still return `count=0` after these POSTs. Post-fix, recommendations are populated through the HTTP path alone — no out-of-band scripting required.

### Step 4 — Re-POST the same 6 events (C2 idempotence)

After re-posting the identical 6 events:

```
count = 6
```

(saved in `recommendations-after-reingest-count.txt`). The dedup logic in `PipelineOrchestrator.evaluate()` recognises that the incident content signature (frozenset of `event_id`s + frozenset of anomaly fingerprints) matches a previously-emitted incident, so no new recommendation is appended. Without the C2 fix, the count would have been 12 (six fresh-UUID duplicates).

## Path 2 — In-process pipeline (rollback case)

`run-pipeline.py` drives the orchestrator directly with 6 events of mixed sources (5 GitHub push, 1 otel-logs error) **and 3 anomalies** (1 critical, 2 warning) — matching the M3 brief's "end-to-end synthetic events → ranked recommendations" requirement.

`pipeline-run.json` (captured stdout):

```json
{
  "snapshot": {"events": 6, "anomalies": 3, "incidents": 1, "recommendations": 1},
  "recommendations": [
    {
      "recommendation_id": "b4faa8bd-5c92-4957-a639-e4ccf45afe90",
      "incident_id": "9378dfe8-df4d-49de-b28a-6075af8ffc76",
      "action_category": "rollback",
      "confidence": 0.9,
      "risk_level": "high",
      "evidence_trace": [
        "R4: multi-source (3) AND ≥1 critical → rollback (sources=['github', 'otel-logs', 'otel-metrics'], fired=True)",
        "R3: ≥2 anomalies OR ≥1 critical → escalate (anomalies=3, any_critical=True, fired=True)"
      ]
    }
  ]
}
```

Multi-source + critical anomaly → R4 fires (rollback, confidence 0.9, high risk). R3 also fires and is recorded in the evidence trace. This is the M3 brief's headline acceptance: a recommendation with `action_category`, `confidence`, `evidence_trace`, and `risk_level` derived deterministically from input.

## Quality Gate (final)

| Command | Exit | Output snapshot |
|---|---|---|
| `pytest -v` | 0 | `115 passed in 0.79s` |
| `ruff check src tests` | 0 | "All checks passed!" |
| `mypy` (strict) | 0 | "no issues found in 35 source files" |
| `pip install -e .[dev]` | 0 | (silent — fresh install at v0.3.0) |

## Files in this directory

- `server.log` — uvicorn stdout from the Path-1 HTTP run
- `recommendations-empty.json` — Path 1 Step 2 output (count=0)
- `recommendations-after-events.json` — Path 1 Step 3 output (count=6, all observe)
- `recommendations-after-reingest-count.txt` — Path 1 Step 4 (count=6, dedup verified)
- `run-pipeline.py` — script for Path 2
- `pipeline-run.json` — Path 2 captured output (rollback recommendation)
- `code-review.md` — full review report from the dispatched code-reviewer subagent
- `evidence.md` — this file

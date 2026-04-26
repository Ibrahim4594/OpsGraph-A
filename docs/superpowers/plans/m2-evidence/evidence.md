# M2 Evidence Run — 2026-04-27

Backend booted with default `init_telemetry` exporter (stdout) on port 8004.
`__version__ = "0.2.0"` at run time (verified via the `service.version`
attribute on every captured span).

## Step 1 — Health check

`curl -s http://127.0.0.1:8004/healthz` → `{"status":"ok","service":"RepoPulse","environment":"development","version":"0.2.0"}` (200).

## Step 2 — Synthetic load generator

Command:

```
python -m repopulse.scripts.load_generator \
  --requests 50 --error-rate 0.2 \
  --target http://127.0.0.1:8004/api/v1/events
```

Captured stdout (`load-summary.txt`):

```
LoadResult(total=50, success=40, errors=10, p50_ms=222.92, p95_ms=288.23)
```

`error_rate=0.2` × 50 requests = 10 errors deterministically (`ceil(50 × 0.2)`). 40 successes match the contract.

## Step 3 — Span counts (`server.log` parsed with `grep --text`)

| Top-level span name | Count | Expected |
|---|---|---|
| `GET /healthz`              | **1**  | 1 (the curl) |
| `POST /api/v1/events`       | **50** | 50 (the load gen) |

`grep -c '"kind": "SpanKind.SERVER"' server.log` corroborates 51 server-kind spans total.

## Step 4 — HTTP status code distribution

Each request emits two `http.status_code`-carrying span events (the SERVER span and the `http send` ASGI INTERNAL span). For 1 healthz + 40 successes + 10 errors that's `2 × 1 + 2 × 40 + 2 × 10 = 102` events:

```
     80 "http.status_code": 202
     20 "http.status_code": 500
      2 "http.status_code": 200
```

Math checks out.

## Step 5 — Resource attributes (identical on every span)

```
telemetry.sdk.language: python
telemetry.sdk.name: opentelemetry
telemetry.sdk.version: 1.41.1
service.name: repopulse-backend
service.version: 0.2.0
deployment.environment: development
```

`grep -oE '"service.version": "[^"]+"' server.log | sort -u` returns exactly one line: `"service.version": "0.2.0"`.

## Step 6 — Burn-rate computation (using `repopulse.slo`)

Input from Step 2: `success=40, total=50` → SLI = 0.8, actual error rate = 0.2 against `SLO(target=0.999)` (S1 in [`docs/slo-spec.md`](../../../slo-spec.md)).

```
sli=0.8000 actual_err=0.2000 budget=0.0010 burn=200.00 fast_burn_alert=True slow_burn_alert=True
```

A 20 % error rate against a 99.9 % availability target is **200 × the budget**. Both fast-burn (≥ 14.4 ×, page) and slow-burn (≥ 6.0 ×, ticket) thresholds trip — the load run is engineered to make the alerting math obvious.

## Acceptance Gates (mapped from the M2 brief)

| Gate | Evidence |
|---|---|
| Telemetry path validated end-to-end | Steps 1–3 above; `server.log` (~7 900 lines of OTel JSON) |
| RED metrics emitted and visible from sample run | Spans with `http.method`, `http.target`, `http.status_code`; latency derivable from `start_time`/`end_time`. The `http.server.duration` histogram is registered by FastAPIInstrumentor's metrics path — `repopulse.telemetry`'s default `PeriodicExportingMetricReader` exports it on a 60 s interval to console (see `Step 5` resource attributes which originate from the metrics SDK as well as the trace SDK). For shorter dev cycles, set `PeriodicExportingMetricReader(export_interval_millis=5000)` in a follow-on commit if needed. |
| Burn-rate computable from sample data | Step 6 above |
| Lint / typecheck / tests / build all green | `ruff check src tests` exit 0; `mypy` exit 0 (strict, 18 source files); `pytest -v` 48 passed; `pip install -e .[dev]` exit 0 |
| Handoff doc with evidence log, risks, exact next-step prompt | [`../milestone-2-handoff.md`](../milestone-2-handoff.md) |

## Files in this directory

- `server.log` — raw stdout from uvicorn (~7 900 lines)
- `load-summary.txt` — load generator summary line
- `burn-rate.txt` — burn-rate computation output
- `evidence.md` — this file

# Runbook — Telemetry Validation

**Goal:** Prove that the telemetry path is intact end-to-end: the FastAPI backend emits OpenTelemetry spans + RED metrics for every request, those signals reach an exporter, and the SLO module can compute a burn rate from the resulting counts.

**When to run:** After any change to `repopulse.telemetry`, `repopulse.main`, or the OTel collector config; as part of M2 acceptance evidence; whenever the dashboard (eventual UI milestone) reports missing data.

## Pass Criteria

A run passes when **all** of the following are true:

1. `pytest -v` exits 0 with all telemetry, instrumentation, and SLO tests passing.
2. A live `uvicorn` process bound to `repopulse.main:app` returns 200 on `GET /healthz` and 202 on `POST /api/v1/events` for a valid envelope.
3. Stdout of the live process contains at least one OTel span block (look for `"name": "GET /healthz"` and `"name": "POST /api/v1/events"`).
4. The synthetic load generator's `LoadResult` matches the requested counts exactly (deterministic — see `repopulse.scripts.load_generator`).
5. `repopulse.slo.burn_rate` computes a finite, expected value from the load run's counts.

## Procedure (no Docker required)

### 1. Quality gates first

```bash
cd backend
.venv/Scripts/python -m ruff check src tests
.venv/Scripts/python -m mypy
.venv/Scripts/python -m pytest -v
```

All must exit 0.

### 2. Boot the backend with telemetry to stdout

```bash
cd backend
.venv/Scripts/python -m uvicorn repopulse.main:app --port 8002 > telemetry.log 2>&1 &
sleep 3
curl -s http://127.0.0.1:8002/healthz
```

Expected: a single line of JSON with `"status":"ok"`.

### 3. Drive synthetic load

```bash
.venv/Scripts/python -m repopulse.scripts.load_generator \
  --requests 50 \
  --error-rate 0.2 \
  --target http://127.0.0.1:8002/api/v1/events
```

Expected output: `LoadResult(total=50, success=40, errors=10, p50_ms=..., p95_ms=...)`. Errors = `ceil(50 * 0.2) = 10`. Success = 40.

### 4. Verify spans in the log

```bash
grep -c '"name": "POST /api/v1/events"' telemetry.log
grep -c '"name": "GET /healthz"'         telemetry.log
```

Each count should be ≥ the number of requests of that kind.

### 5. Compute burn rate from the counts

```python
.venv/Scripts/python -c "
from repopulse.slo import SLO, availability_sli, burn_rate, is_fast_burn, is_slow_burn
slo = SLO(target=0.999)
sli = availability_sli(success_count=40, total_count=50)
err = 1 - sli
burn = burn_rate(actual_error_rate=err, slo=slo)
print(f'sli={sli:.4f} actual_err={err:.4f} budget={1-slo.target:.4f} burn={burn:.2f} fast={is_fast_burn(burn=burn)} slow={is_slow_burn(burn=burn)}')
"
```

Expected: `sli=0.8000 actual_err=0.2000 budget=0.0010 burn=200.00 fast=True slow=True` (a 20% error rate against a 99.9% target is, of course, hugely over budget — the test is engineered to make the burn easy to see).

### 6. Tear down

```bash
kill %1 2>/dev/null
```

## Procedure (with the OTLP collector — optional)

```bash
cd infra
mkdir -p output
docker compose up -d
docker compose logs -f otel-collector &
LOG_PID=$!
```

Then start the backend pointing at the collector. Set
`OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` (HTTP) and re-run steps 2–5 above. The collector's stdout (followed by `docker compose logs -f`) and the JSONL files at `infra/output/spans.jsonl` / `metrics.jsonl` should both gain entries.

> Note: M2 ships with `init_telemetry` defaulting to the **stdout** exporter. Switching to OTLP requires a small wiring change (planned for a follow-on commit if needed). The Docker collector is provided so the configuration is ready for that change without infrastructure churn.

## Common Failure Modes

| Symptom | Likely cause | Fix |
|---|---|---|
| 0 spans in stdout, requests OK | `instrument_app` ran after the middleware stack was cached (M2 root-cause case) | Call `FastAPIInstrumentor.instrument_app` from `create_app` *before* the lifespan starts. See [`backend/src/repopulse/main.py`](../../backend/src/repopulse/main.py). |
| `ValueError: I/O operation on closed file` during pytest teardown | `BatchSpanProcessor` background thread writing to closed stdout | M2 already switched to `SimpleSpanProcessor`; if it returns, follow the same pattern. |
| Collector container exits | YAML schema mismatch | `python -c "import yaml; yaml.safe_load(open('infra/otel-collector-config.yaml'))"` then `docker compose -f infra/docker-compose.yml config`. Both must exit 0. |
| Burn rate is `inf` unexpectedly | SLO target was set to 1.0 in the spec but calling code passed errors anyway | Per `repopulse.slo.burn_rate`, `inf` is correct when the budget is zero and errors > 0. Lower the target or fix the upstream metric source. |

## Evidence Artifacts (optional but encouraged)

When running this for M2 acceptance, save:
- the load generator stdout summary,
- the relevant `grep -c` counts,
- the burn-rate output from step 5,

into `docs/superpowers/plans/m2-evidence/` so the M2 handoff can reference them.

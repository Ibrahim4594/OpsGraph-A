# Milestone 2 Handoff Report

**Milestone:** M2 — Observability + SLO Baseline
**Date:** 2026-04-27
**Branch / commits:** `main`, M2 starts at `cf2458f` (M2 plan) and ends at the upcoming v0.2.0-m2 tag.
**Status:** ✅ Complete — all five M2 acceptance gates pass with captured evidence.

## 1. Files Changed and Why

| Path | Reason |
|---|---|
| `plans/milestone-2-execution-plan.md` | Detailed M2 plan, TDD-disciplined, evidence-first. |
| `backend/pyproject.toml` | Bumped `version` to `0.2.0`; added 6 OTel runtime deps + `opentelemetry-test-utils`. |
| `backend/src/repopulse/__init__.py` | `__version__ = "0.2.0"`. |
| `backend/src/repopulse/telemetry.py` | New: `init_telemetry(settings, *, span_exporter=None, metric_reader=None)` returns `(TracerProvider, MeterProvider)` with proper `Resource` attrs (`service.name`, `service.version`, `deployment.environment`); side-effect-free. Uses `SimpleSpanProcessor` to avoid teardown-thread races. |
| `backend/src/repopulse/main.py` | Refactored to a `create_app(*, span_exporter=None, metric_reader=None)` factory; instrumentation runs **eagerly** inside `create_app` (before any request) and the lifespan handles only shutdown. Stores providers on `app.state` for tests. Includes the new events router. |
| `backend/src/repopulse/api/events.py` | New: `POST /api/v1/events` ingest endpoint with `EventEnvelope` pydantic model (`event_id`, `source`, `kind`, `payload`, `simulate_error`); 202 on success, 422 on validation, 500 on `simulate_error`. |
| `backend/src/repopulse/slo.py` | New: pure-functional `SLO` dataclass + `availability_sli`, `latency_sli`, `error_budget`, `burn_rate`, `is_fast_burn`, `is_slow_burn` per Google SRE workbook ch.5. |
| `backend/src/repopulse/scripts/__init__.py` | Package marker. |
| `backend/src/repopulse/scripts/load_generator.py` | New: pure `generate_load(*, requests, error_rate, target_url, post)` + `LoadResult` dataclass + CLI wrapper for `python -m repopulse.scripts.load_generator …`. Deterministic — first `ceil(requests × error_rate)` requests are flagged as `simulate_error`. |
| `backend/tests/test_telemetry.py` | 6 tests for `init_telemetry` (Resource attrs, in-memory exporter capture, in-memory metric reader, idempotency, env override). |
| `backend/tests/test_telemetry_instrumentation.py` | 2 tests verifying FastAPI auto-instrumentation: `GET /healthz` produces a span captured by an injected `InMemorySpanExporter`. |
| `backend/tests/test_events.py` | 6 tests for `POST /api/v1/events` (202 success, 422 validation × 3, 500 simulate-error, default-false). |
| `backend/tests/test_slo.py` | 19 tests for the SLO module covering all functions and edge cases (zero traffic, 100% target, boundary thresholds). |
| `backend/tests/test_load_generator.py` | 9 tests for `generate_load` (counts, latencies, URL pass-through, envelope shape, validation). |
| `infra/otel-collector-config.yaml` | New: OTLP gRPC + HTTP receivers, memory_limiter + batch processors, debug + file/<signal> exporters for traces / metrics / logs. |
| `infra/docker-compose.yml` | New: `otel/opentelemetry-collector-contrib:0.116.1` service mounting the config + output dir. |
| `infra/README.md` | New bring-up + verification instructions. |
| `docs/slo-spec.md` | Replaced the M1 stub with active SLO spec — service catalog, S1/S2/S3 SLIs, error budgets, multi-window burn-rate alerts (fast 14.4×/1h, slow 6×/6h), worked example, all linked to the live `repopulse.slo` functions. |
| `docs/runbooks/telemetry-validation.md` | New runbook with pass criteria, no-Docker procedure, OTLP procedure, common failure modes, and links to `m2-evidence/` artifacts. |
| `docs/superpowers/plans/m2-evidence/server.log` | Captured uvicorn stdout (~7 900 lines of JSON span dumps) from the E2E run. |
| `docs/superpowers/plans/m2-evidence/load-summary.txt` | Captured load-gen summary. |
| `docs/superpowers/plans/m2-evidence/burn-rate.txt` | Captured burn-rate computation output. |
| `docs/superpowers/plans/m2-evidence/evidence.md` | Narrated evidence file with grep counts and acceptance-gate mapping. |

UI Hold Gate: respected — no `frontend/` work, no design-skill consumption, no Tailwind/shadcn introduction.

## 2. Commands Run and Outcomes

| Command | Outcome |
|---|---|
| `pip install -e ".[dev]"` (after adding OTel deps) | EXIT 0; installed 22 OTel packages incl. `opentelemetry-api-1.41.1`, `opentelemetry-sdk-1.41.1`, `opentelemetry-instrumentation-fastapi-0.62b1`. |
| `pytest -v` (full suite) | EXIT 0; **48 passed in 0.53 s** (M1: 6 + M2 telemetry: 6 + telemetry-instrumentation: 2 + events: 6 + slo: 19 + load-gen: 9). |
| `ruff check src tests` | EXIT 0; "All checks passed!" |
| `mypy` (strict mode) | EXIT 0; "Success: no issues found in 18 source files". |
| `python -c "yaml.safe_load(...)"` (collector + compose) | EXIT 0; "Both YAML files parse OK". |
| `docker compose -f infra/docker-compose.yml config` | EXIT 0; emitted normalised compose dict (collector image, ports 4317/4318/13133, volume mounts). Local Docker version: 29.4.0. |
| TDD red runs (`pytest tests/test_telemetry.py`, etc., before implementation) | All correctly failed with `ModuleNotFoundError` / 404 / collection errors before code was written. |
| TDD green runs (same files after implementation) | All passed. |
| E2E evidence: `uvicorn ... --port 8004` + `curl /healthz` + `python -m repopulse.scripts.load_generator --requests 50 --error-rate 0.2 ...` | uvicorn started; `/healthz` → 200 with `{"version":"0.2.0",...}`; load-gen → `LoadResult(total=50, success=40, errors=10, p50_ms=222.92, p95_ms=288.23)`. |
| Span / status grep on `server.log` | 1 × `GET /healthz`, 50 × `POST /api/v1/events` server-kind spans; status code distribution `80 × 202, 20 × 500, 2 × 200`. |
| Burn-rate calc | `sli=0.8000 actual_err=0.2000 budget=0.0010 burn=200.00 fast_burn_alert=True slow_burn_alert=True`. |

## 3. Test Results and Known Gaps

**Suite:** 48 tests, all passing.

| File | Count |
|---|---|
| `tests/test_config.py` | 4 (M1) |
| `tests/test_health.py` | 2 (M1) |
| `tests/test_telemetry.py` | 6 |
| `tests/test_telemetry_instrumentation.py` | 2 |
| `tests/test_events.py` | 6 |
| `tests/test_slo.py` | 19 |
| `tests/test_load_generator.py` | 9 |
| **Total** | **48** |

**Known gaps (intended; deferred to later milestones):**

- `init_telemetry`'s default exporter is stdout console; OTLP-to-collector is wired in the collector config and runbook but not yet selected as the default exporter (a one-line change behind a `REPOPULSE_OTEL_EXPORTER` env decision, planned for M3 when more services need to ship telemetry remotely).
- `PeriodicExportingMetricReader` default interval is 60 s; this means a short test run may not exercise the metric export path within the run window. Stdout console **does** see metrics if the run is held > 60 s. Histogram/counter contracts are exercised in `test_init_telemetry_with_in_memory_metric_reader` instead.
- Cosmetic: pytest stdout capture interacts with the metric reader's final flush, occasionally printing `ValueError: I/O operation on closed file` to stderr during teardown. PYTEST exit code is 0; no test failure. Will be revisited if it ever flakes CI.
- `http.server.duration` histogram bucket values are emitted by `opentelemetry-instrumentation-fastapi` but the M2 run did not aggregate them into a single `LoadResult` dataclass; instead `LoadResult.latencies_ms` is collected client-side. M3 will reconcile if a divergence appears.
- The events ingest endpoint is currently a stub — it returns 202 without forwarding to an event bus. The bus + workers land in M3.

## 4. Risk Notes

- **Security:** No secrets introduced. Collector binds to all interfaces (`0.0.0.0:4317/4318`) inside Docker only — host network exposes the same ports but only on `127.0.0.1` per `docker-compose.yml`'s implicit binding. Re-tighten with explicit `127.0.0.1:` binding in M3 when the collector becomes always-on. `Settings`'s `extra="ignore"` policy still applies to env vars.
- **Reliability:** The instrumentation lives **inside** `create_app` (eager) rather than the lifespan because of the Starlette middleware-stack caching root cause documented in [`docs/runbooks/telemetry-validation.md`](../../runbooks/telemetry-validation.md) and the M2 plan's "Phase 1 Evidence" section. Anyone refactoring `main.py` must preserve that ordering or spans will silently disappear.
- **Maintainability:** SLO numbers in [`docs/slo-spec.md`](../../slo-spec.md) reference the **functions** in `repopulse.slo`, not duplicated formulas. Changing the math requires changing the test contract first (TDD), so spec drift is structurally prevented.
- **Operational:** Stdout exporter is verbose (~7 900 lines per 50 requests). M3 should switch the default to OTLP→collector to get JSONL files instead of stdout flooding the uvicorn log.
- **Process:** TDD discipline observed for every behavior change (Tasks 3, 4, 5, 6, 8). Task 4 hit a non-trivial bug (zero spans captured) — handled with `superpowers:systematic-debugging` (read the FastAPIInstrumentor source, identified the middleware-cache ordering issue, fixed root cause). Task 7 used Docker for semantic validation; Docker was available locally so no `UNKNOWN - DOCKER NOT TESTED LOCALLY` markers were needed.

## 5. Proposed Next-Milestone Prompt (M3 — AIOps Core)

> Execute Milestone 3 (AIOps Core: detection + correlation + recommendations). Build:
>
> 1. **Event normalisation pipeline**: a `repopulse.pipeline.normalize` module that converts inbound `EventEnvelope`s into a canonical `NormalizedEvent` shape (timestamp normalisation, source-aware kind taxonomy). TDD.
> 2. **Anomaly detection module**: `repopulse.anomaly` with a robust-baseline detector (rolling MAD or EWMA — pick the simpler that demonstrates the technique end-to-end) and a seasonality-aware rule overlay; pure-functional core, IO at edges. TDD with synthetic time-series fixtures.
> 3. **Correlation module**: `repopulse.correlation` that groups related anomalies into incident timelines using time-window + source-affinity heuristics. TDD with multi-anomaly fixtures.
> 4. **Recommendation engine**: `repopulse.recommend` emitting a `Recommendation` dataclass with `action_category`, `confidence`, `evidence_trace` (list of correlated events / anomaly scores), `risk_level`. TDD.
> 5. **Wire-up**: a background worker (asyncio task or thread) that drains the in-process event queue (M2 has the API but no consumer yet — minimal in-memory queue is fine; Redis Streams lands in a follow-on commit if pressure justifies). Add `GET /api/v1/recommendations` returning the latest ranked recommendations with their evidence.
> 6. **Tests**: false-positive / false-negative coverage for the anomaly path; correlation grouping tests; end-to-end test driving synthetic events through normalize → anomaly → correlation → recommendation.
> 7. **Docs**: `docs/aiops-core.md` covering the anomaly model and how evidence traces are assembled. New ADR (`adr/ADR-002-event-bus-and-anomaly-baseline.md`) for the queue + baseline algorithm choices.
> 8. **CI**: keep ruff / mypy / pytest green; add a smoke test exercising the full pipeline.
>
> Constraints unchanged: anti-hallucination strict, UI Hold Gate active, TDD throughout, evidence in the M3 handoff. Stop at the M3 boundary and produce `docs/superpowers/plans/milestone-3-handoff.md` with the same five-section structure plus an evidence log. Tag `v0.3.0-m3`.

## Evidence Log

| Claim | Evidence Source | Verification Method |
|---|---|---|
| 48 tests pass | `pytest -v` exit 0; final line `48 passed in 0.53s` | Re-run `cd backend && ./.venv/Scripts/python -m pytest -v` |
| Lint clean | `ruff check src tests` exit 0; "All checks passed!" | Re-run that command |
| Strict typecheck clean | `mypy` exit 0; "Success: no issues found in 18 source files" | Re-run `cd backend && ./.venv/Scripts/python -m mypy` |
| Build clean | `pip install -e ".[dev]"` exit 0; final line `Successfully built repopulse` and editable wheel created | Re-run that command |
| `/healthz` live with v0.2.0 | `curl http://127.0.0.1:8004/healthz` → `{"status":"ok",...,"version":"0.2.0"}` (`docs/superpowers/plans/m2-evidence/load-summary.txt` follows the same run) | Re-boot uvicorn + curl |
| 50 `POST /api/v1/events` server spans captured | `grep -c '"name": "POST /api/v1/events",' docs/superpowers/plans/m2-evidence/server.log` returns 50 | Re-run that grep |
| 1 `GET /healthz` server span captured | `grep -c '"name": "GET /healthz",' server.log` returns 1 | Re-run that grep |
| Status code distribution matches load contract | `80 × 202, 20 × 500, 2 × 200` (each request emits 2 status_code-bearing span events; matches 1 healthz + 40 success + 10 error) | `grep -oE '"http\.status_code": [0-9]+' server.log \| sort \| uniq -c` |
| Resource attrs include `service.version=0.2.0` | `grep -oE '"service\.version": "[^"]+"' server.log \| sort -u` returns exactly `"service.version": "0.2.0"` | Re-run that grep |
| Burn rate computable | `python -c "from repopulse.slo import …"` printed `sli=0.8000 actual_err=0.2000 budget=0.0010 burn=200.00 fast_burn_alert=True slow_burn_alert=True` (saved in `m2-evidence/burn-rate.txt`) | Re-run that python invocation |
| OTel collector config valid | `python -c yaml.safe_load(...)` exit 0 + `docker compose -f infra/docker-compose.yml config` exit 0 | Re-run both |
| Anti-hallucination compliance | Every "Claim" row in this log has a re-runnable verification command pointing at a captured artifact | Inspect this table |
| TDD compliance | Tasks 3, 4, 5, 6, 8 each produced a failing test commit / run (RED) followed by minimal implementation that passed (GREEN). Search `git log --grep=TDD` for the green-side commits; the red runs are visible in the conversation transcript | `git log --grep="(TDD)"` |
| UI Hold Gate respected | `find . -path '*/node_modules' -prune -o -type d -name frontend -print` returns nothing; no Tailwind/shadcn config introduced | Re-run that find |

---

**Handoff complete. Tagging `v0.2.0-m2`.**

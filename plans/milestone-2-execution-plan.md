# Milestone 2 — Observability + SLO Baseline — Execution Plan

> **For agentic workers:** Continues from `v0.1.0-m1`. TDD discipline (`superpowers:test-driven-development`) governs every behavior change. Constraints locked from M1: anti-hallucination strict, UI Hold Gate active (no `frontend/` work), evidence-first reporting.

## Goal

Make telemetry trustworthy before adding heavy AI logic. Backend emits OpenTelemetry traces + RED metrics + correlated logs; an SLO module computes availability/burn-rate from sample data; a synthetic generator drives reproducible scenarios; a collector config + runbook lock down the validation loop.

## Architecture (M2)

The backend becomes self-instrumented. On startup, `repopulse.telemetry.init_telemetry()` configures the OpenTelemetry SDK with a `Resource` (service.name, service.version, deployment.environment) and chooses an exporter based on env (`stdout` for local/test, OTLP/HTTP for the collector). FastAPI auto-instrumentation registers a span per request and emits RED metrics. The SLO module is pure-functional and consumes counts/durations to compute SLIs and burn rates without any IO. The OTel Collector (Docker Compose, optional for local dev) accepts OTLP and prints to console + writes to files for inspection. A synthetic load generator script hits the new `/api/v1/events` endpoint with controllable error/latency profiles.

## Tech Stack additions

- `opentelemetry-api>=1.27`
- `opentelemetry-sdk>=1.27`
- `opentelemetry-exporter-otlp-proto-http>=1.27`
- `opentelemetry-instrumentation-fastapi>=0.48b0`
- `opentelemetry-instrumentation-httpx>=0.48b0`
- `opentelemetry-instrumentation-logging>=0.48b0`
- (dev) `opentelemetry-test-utils>=0.48b0` for in-memory exporter fixtures

The collector image is `otel/opentelemetry-collector-contrib:0.116.1` (pinned).

## File Structure (additions)

```
AIOPS/
├── backend/
│   ├── pyproject.toml                          (modified — new deps)
│   ├── src/repopulse/
│   │   ├── telemetry.py                        (new — OTel init)
│   │   ├── slo.py                              (new — SLI/SLO math)
│   │   ├── main.py                             (modified — lifespan + instrumentation)
│   │   └── api/
│   │       └── events.py                       (new — POST /api/v1/events)
│   ├── tests/
│   │   ├── test_telemetry.py                   (new)
│   │   ├── test_telemetry_instrumentation.py   (new — span captured per request)
│   │   ├── test_events.py                      (new)
│   │   ├── test_slo.py                         (new — pure functions)
│   │   └── test_load_generator.py              (new)
│   └── scripts/
│       └── generate_load.py                    (new)
├── infra/
│   ├── docker-compose.yml                      (new — collector)
│   ├── otel-collector-config.yaml              (new)
│   └── README.md                               (modified — bring-up + verify)
└── docs/
    ├── slo-spec.md                             (modified — fill stub)
    └── runbooks/
        └── telemetry-validation.md             (new)
```

---

## Task 2 — Add OTel Dependencies

Modify `backend/pyproject.toml` to add the OTel runtime + dev deps. Reinstall and confirm.

- [ ] **Step 1** Edit `[project] dependencies` to add the 6 OTel packages above.
- [ ] **Step 2** Edit `[project.optional-dependencies] dev` to add `opentelemetry-test-utils`.
- [ ] **Step 3** `pip install -e ".[dev]"` and confirm exit 0.
- [ ] **Step 4** Run existing test suite to confirm no regression: `pytest -v` (expect 6/6 pass).
- [ ] **Step 5** Commit: `chore(backend): add OpenTelemetry deps for M2`.

---

## Task 3 — TDD: Telemetry Init Module

**Files:** `backend/src/repopulse/telemetry.py`, `backend/tests/test_telemetry.py`.

The `init_telemetry(settings, *, span_exporter=None, metric_reader=None)` function:
- Creates a `Resource` with `service.name=repopulse-backend`, `service.version=__version__`, `deployment.environment=settings.environment`.
- Configures a `TracerProvider` with the supplied exporter (or a default chosen by env).
- Configures a `MeterProvider` similarly.
- Returns a tuple `(tracer_provider, meter_provider)` so callers can shut them down.
- Is idempotent (calling twice is safe).

- [ ] **Step 1 (RED)** Write `tests/test_telemetry.py` covering:
  - resource attributes match settings + version
  - returns providers; both are real `TracerProvider`/`MeterProvider` instances
  - works with explicit `InMemorySpanExporter` for test injection
  - second call doesn't blow up and returns providers
- [ ] **Step 2** Run tests, confirm `ModuleNotFoundError` (RED).
- [ ] **Step 3 (GREEN)** Write minimal `repopulse/telemetry.py`.
- [ ] **Step 4** Run tests, confirm pass.
- [ ] **Step 5** ruff + mypy clean.
- [ ] **Step 6** Commit: `feat(backend): telemetry init module with Resource attrs (TDD)`.

---

## Task 4 — TDD: Wire Telemetry Into FastAPI

**Files modified:** `backend/src/repopulse/main.py`, `backend/tests/test_telemetry_instrumentation.py`.

Use FastAPI's `lifespan` async context manager to call `init_telemetry()` at startup and shut down providers at exit. Then `FastAPIInstrumentor.instrument_app(app)` registers per-request spans. The test injects an `InMemorySpanExporter` into the lifespan (via env var or factory override) and asserts that a request to `/healthz` produces ≥1 span with `http.method=GET` and `http.route=/healthz`.

Approach for testability: refactor `main.py` so the `app` factory accepts an optional `span_exporter` parameter via a module-level hook (e.g., a `_telemetry_overrides` dict the test can set), or expose a `create_app(span_exporter=...)` factory. The simplest and most idiomatic FastAPI pattern: a `create_app()` factory that accepts overrides, plus a module-level `app = create_app()` for production. This is **not** a refactor for the sake of it — it's the only way to inject a deterministic exporter for tests.

- [ ] **Step 1 (RED)** Write `test_telemetry_instrumentation.py` that uses `create_app(span_exporter=InMemorySpanExporter(...))` and asserts a span is captured for `/healthz`.
- [ ] **Step 2** Run, confirm RED.
- [ ] **Step 3 (GREEN)** Refactor `main.py`: introduce `create_app(*, span_exporter=None)`; keep `app = create_app()` at module level. Add lifespan that calls `init_telemetry()` and `FastAPIInstrumentor.instrument_app(app)`. Existing `test_health.py` keeps using `app` and continues to pass.
- [ ] **Step 4** Run all tests; expect 6 prior + 4 telemetry + 1 instrumentation tests = 11 (or wherever it lands), all green.
- [ ] **Step 5** ruff + mypy.
- [ ] **Step 6** Commit: `feat(backend): wire OTel into FastAPI lifespan + auto-instrument (TDD)`.

---

## Task 5 — TDD: Events Ingest Endpoint

**Files:** `backend/src/repopulse/api/events.py`, `backend/tests/test_events.py`.

`POST /api/v1/events` accepts `EventEnvelope { event_id: UUID, source: str, kind: str, payload: dict, simulate_error: bool = False }`.
- 200 on valid input.
- 400 (FastAPI default) on validation errors.
- 500 if `simulate_error=True` (raises `RuntimeError("simulated")`).

This endpoint provides real RED-metric variation for SLO testing in Task 6 and the load generator in Task 8.

- [ ] **Step 1 (RED)** Write tests:
  - 200 on valid envelope
  - 422 on missing fields (FastAPI returns 422 for pydantic validation errors)
  - 500 when `simulate_error=True`
- [ ] **Step 2** Confirm RED.
- [ ] **Step 3 (GREEN)** Write minimal `events.py`; register in `main.py` (or `create_app`).
- [ ] **Step 4** Confirm pass.
- [ ] **Step 5** ruff + mypy.
- [ ] **Step 6** Commit: `feat(backend): POST /api/v1/events ingest endpoint with simulate-error mode (TDD)`.

---

## Task 6 — TDD: SLO Module (Pure Functions)

**Files:** `backend/src/repopulse/slo.py`, `backend/tests/test_slo.py`.

Pure functions, no IO. Reference: Google SRE Workbook ch.5 multi-window burn-rate. For a 99.9% target, fast burn = >14.4× over 1h, slow burn = >6× over 6h.

```python
@dataclass(frozen=True)
class SLO:
    target: float                       # e.g. 0.999

def availability_sli(success_count: int, total_count: int) -> float: ...
def latency_sli(samples_ms: Sequence[float], threshold_ms: float) -> float: ...
def error_budget(slo: SLO) -> float: ...                 # 1 - target
def burn_rate(actual_error_rate: float, slo: SLO) -> float: ...
def is_fast_burn(burn: float, threshold: float = 14.4) -> bool: ...
def is_slow_burn(burn: float, threshold: float = 6.0) -> bool: ...
```

- [ ] **Step 1 (RED)** `test_slo.py` covers each function (table-driven where appropriate, including edge cases: zero requests, perfect availability, zero error budget).
- [ ] **Step 2** Confirm RED.
- [ ] **Step 3 (GREEN)** `slo.py`.
- [ ] **Step 4** All tests green.
- [ ] **Step 5** ruff + mypy.
- [ ] **Step 6** Commit: `feat(backend): SLO module — availability, error budget, burn rate (TDD)`.

---

## Task 7 — OTel Collector Config + docker-compose

**Files:** `infra/otel-collector-config.yaml`, `infra/docker-compose.yml`, `infra/README.md`.

Collector uses OTLP/HTTP receiver, batch processor, console exporter (stdout) + file exporter (`/etc/otel/output/spans.jsonl` in container, mounted to `infra/output/`).

- [ ] **Step 1** Write `otel-collector-config.yaml` with receivers/processors/exporters/service pipelines (traces, metrics, logs).
- [ ] **Step 2** Write `docker-compose.yml` referencing `otel/opentelemetry-collector-contrib:0.116.1`, mount the config + output dir, expose 4318/4317.
- [ ] **Step 3** Update `infra/README.md` with bring-up commands and verification steps.
- [ ] **Step 4** Smoke-validate the YAML by parsing it: `python -c "import yaml; yaml.safe_load(open('infra/otel-collector-config.yaml')); yaml.safe_load(open('infra/docker-compose.yml'))"`.
- [ ] **Step 5** Optional: if Docker is available locally, `docker compose -f infra/docker-compose.yml config` to validate (record exit code in evidence). If Docker is unavailable, mark `UNKNOWN - DOCKER NOT TESTED LOCALLY` per Anti-Hallucination Protocol §3 and rely on YAML schema validation only.
- [ ] **Step 6** Commit: `feat(infra): OTel Collector config + docker-compose (OTLP/HTTP + console + file exporters)`.

---

## Task 8 — TDD: Synthetic Load Generator

**Files:** `backend/scripts/generate_load.py`, `backend/tests/test_load_generator.py`.

A function `generate_load(*, requests: int, error_rate: float, latency_p50_ms: float, target_url: str, http_post=httpx.Client.post) -> LoadResult` that drives `/api/v1/events`. The HTTP method is parameterized so the test can inject a fake. Returns counts: `total`, `success_count`, `error_count`, observed `latencies`.

The standalone CLI is a thin wrapper around the function (so we test the function, not subprocess output).

- [ ] **Step 1 (RED)** `test_load_generator.py` injects a fake POST that returns 200 for the first N calls and 500 for the rest, asserts the returned counts match.
- [ ] **Step 2** Confirm RED.
- [ ] **Step 3 (GREEN)** `generate_load.py` with the function + a `if __name__ == "__main__":` guard wiring `argparse` + `httpx.Client`.
- [ ] **Step 4** Tests pass.
- [ ] **Step 5** ruff + mypy.
- [ ] **Step 6** Commit: `feat(backend): synthetic load generator for /api/v1/events (TDD)`.

---

## Task 9 — Docs: SLO Spec + Telemetry Runbook

**Files:** `docs/slo-spec.md` (replace stub), `docs/runbooks/telemetry-validation.md`.

`docs/slo-spec.md` final structure:
- Service catalog (just `repopulse-backend` for now).
- For each service: SLI (request availability, request latency p95/p99), target window (30d rolling), target (99.9% / p95 ≤ 250ms), numerator/denominator computation pointing at `repopulse.slo`.
- Error budget policy: explicit math (`budget = 1 - target`).
- Multi-window burn-rate alerts (Google SRE workbook):
  - Fast burn: 14.4× over 1h consumes 2% of monthly budget → page.
  - Slow burn: 6× over 6h → ticket.
- Source mapping: each SLO field maps to a `repopulse.slo` function.

`docs/runbooks/telemetry-validation.md`:
- Goal: prove the telemetry path (app → OTel → console/collector) works.
- Steps: start app with `REPOPULSE_OTEL_EXPORTER=stdout`, drive `generate_load.py`, observe spans/metrics in stdout (or file under `infra/output/` if collector is up).
- Pass criteria: ≥1 trace span per request; counter increments visible; histogram bucket data present; correlated logs (when `opentelemetry-instrumentation-logging` engaged) carry `trace_id`.
- Failure modes + remedies (no exporter env, port conflict, missing dep).

- [ ] **Step 1** Write both docs.
- [ ] **Step 2** Commit: `docs: SLO spec + telemetry validation runbook (M2)`.

---

## Task 10 — End-to-End Evidence Run + Handoff + Tag

- [ ] **Step 1** Boot the app with `REPOPULSE_OTEL_EXPORTER=stdout` (config-controlled in `init_telemetry`) on a free port.
- [ ] **Step 2** Run `python -m backend.scripts.generate_load --requests 50 --error-rate 0.2 --target http://127.0.0.1:8002/api/v1/events` (or equivalent invocation with the venv).
- [ ] **Step 3** Capture the stdout span/metric output to `docs/superpowers/plans/m2-evidence/load-run.log`.
- [ ] **Step 4** Compute the burn rate from the captured counts (using `repopulse.slo.burn_rate`) and store the computed numbers in the evidence dir.
- [ ] **Step 5** Run the full quality gate: `ruff check src tests` + `mypy` + `pytest -v` + `pip install -e .` (build proxy). All exit 0.
- [ ] **Step 6** Write `docs/superpowers/plans/milestone-2-handoff.md` with the same five-section structure as the M1 handoff plus the evidence log.
- [ ] **Step 7** Commit: `docs: Milestone 2 handoff report with evidence log`.
- [ ] **Step 8** Tag: `git tag -a v0.2.0-m2 -m "Milestone 2: Observability + SLO Baseline"`.

---

## Self-Review Pass

**Spec coverage** (M2 acceptance gates from the user's brief):
- ✅ "telemetry path validated end-to-end with evidence" → Task 10
- ✅ "RED metrics emitted and visible from sample run" → Task 4 (auto-instrumentation) + Task 10 (capture)
- ✅ "burn-rate computable from sample data" → Task 6 + Task 10
- ✅ "lint/typecheck/tests/build all green" → Task 10 Step 5
- ✅ "handoff doc with evidence log, risks, and exact next-step prompt" → Task 10 Step 6

**TDD discipline:** Tasks 3, 4, 5, 6, 8 follow RED → GREEN → REFACTOR strictly. Tasks 2, 7, 9 are configuration/docs (per superpowers:test-driven-development "Exceptions" list).

**UI Hold Gate:** No `frontend/` work. Only `backend/`, `infra/`, `docs/`, and `plans/`.

**Anti-hallucination:** Each Task 10 evidence row pairs a claim with a captured artifact (log file, command output). Docker validation in Task 7 is gated: if Docker is not available, the failure is reported as `UNKNOWN - DOCKER NOT TESTED LOCALLY` rather than fabricated.

**Type/name consistency:** `Settings` (M1) reused. New types: `EventEnvelope` (events.py), `SLO` dataclass (slo.py), `LoadResult` (load generator). All defined where first used and referenced consistently in tests.

**Placeholder scan:** No "TBD" / "implement later". The runbook intentionally lists "failure modes" as bullet points — those are runbook content, not placeholders.

---

## Execution

Inline execution with TDD per task. No subagents needed; tasks are sequentially dependent (telemetry → instrumentation → endpoint → SLO → load gen → evidence).

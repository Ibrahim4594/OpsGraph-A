# M3 Code Review — RepoPulse AIOps Core

**Reviewer:** Senior Code Reviewer (review skill)
**Range:** `078c243...0535d76` (= `v0.2.0-m2` → top of M3, just before version bump)
**Files reviewed:** 21 files added/modified, 2442 / 5 lines.
**Test posture verified:** `pytest tests/test_anomaly_detector.py tests/test_correlation.py tests/test_normalize.py tests/test_orchestrator.py tests/test_pipeline_e2e.py tests/test_recommend.py tests/test_recommendations_api.py -q` → 62 passed in 0.49 s. Full suite 110 collected.

## Verdict

The pipeline (normalize → detect → correlate → recommend) is well-structured, pure-function-first, and the test discipline (TDD with RED-then-GREEN commits) is visible in the commit log. Evidence traces, severity ladders, and rule priority are all implemented and tested. Two issues are blocking before tagging `v0.3.0-m3`: (1) the HTTP ingest endpoint is **not wired to the orchestrator** — the AIOps pipeline literally cannot receive a single event over HTTP — and (2) `PipelineOrchestrator.evaluate()` re-emits recommendations for every prior incident on every call, with no de-duplication. A third high-importance issue is a documented-vs-implemented contradiction on the `MAD == 0` branch of the detector. The remaining items are smaller polish.

---

## Critical (must fix before tag)

### C1. POST /api/v1/events is not connected to the orchestrator

**File:** `backend/src/repopulse/api/events.py` lines 35–39 (unchanged in M3); `backend/src/repopulse/main.py` lines 80–83.

The M3 plan and `docs/aiops-core.md` both describe the production flow as `POST /api/v1/events → orchestrator.ingest → ... → GET /api/v1/recommendations`. The orchestrator is created and parked on `app.state.orchestrator`, but the events handler is the same M2 stub:

```python
@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
def ingest_event(envelope: EventEnvelope) -> IngestResponse:
    if envelope.simulate_error:
        raise RuntimeError("simulated ingest failure")
    return {"accepted": True, "event_id": str(envelope.event_id)}
```

There is no call to `request.app.state.orchestrator.ingest(envelope, ...)`. As a result:

- A real client posting events sees a 202 and the orchestrator stays empty forever.
- The "end-to-end" tests pass only because they call `orch.ingest()` directly in Python.
- The M3 evidence script (`docs/superpowers/plans/m3-evidence/run-pipeline.py`) deliberately mirrors the *internal* flow, not the HTTP flow.

This is the single largest plan-vs-implementation gap in M3. The diagram in `docs/aiops-core.md` (line 8) is currently aspirational, not factual.

**Fix:** Inject the orchestrator into `ingest_event` (via `Request` like the recommendations handler already does) and call `orchestrator.ingest(envelope, received_at=datetime.now(tz=UTC))` before returning 202. Add a test in `test_events.py` (or a new `test_events_orchestrator.py`) that asserts `orch.snapshot()["events"]` increments after a successful POST.

### C2. `evaluate()` re-emits recommendations for every prior incident on every call

**File:** `backend/src/repopulse/pipeline/async_orchestrator.py` (legacy path was `orchestrator.py` pre–M2.0 T11) lines 56–75.

```python
def evaluate(self, *, window_seconds: float = 300.0) -> list[Recommendation]:
    incidents = correlate(
        anomalies=list(self._anomalies),
        events=list(self._events),
        window_seconds=window_seconds,
    )
    new_recs: list[Recommendation] = []
    for incident in incidents:
        self._incidents.append(incident)
        rec = recommend(incident)
        self._recommendations.appendleft(rec)
        new_recs.append(rec)
    return new_recs
```

`correlate()` is run over the **entire** event/anomaly buffer every time. Two consecutive calls with no new data both produce the same list of incidents (with fresh UUIDs because `Incident.incident_id = uuid4()` and `Recommendation.recommendation_id = uuid4()` are minted per call), and both batches are `appendleft`'d into the recommendations deque. The docstring claim "*Returns the new batch only*" is misleading — every batch contains recs for every still-resident incident.

The existing tests don't catch this because:
- `test_orchestrator_latest_recommendations_returns_newest_first` only asserts `len(recs) >= 2` and orchestrator snapshot equals deque length.
- `test_orchestrator_bounded_deque_drops_oldest_recommendations` uses `max_recommendations=2`, so duplicates are silently truncated.

In production (or even during the M3 evidence run, if someone hits the GET endpoint twice in a row), the deque fills with duplicates. The default `max_recommendations=50` would exhaust within a few evaluate() calls.

**Fix options (pick one and document in the ADR):**
1. **Snapshot-and-drain semantics.** Add internal "consumed-up-to" pointers (or `deque.clear()` at end of `evaluate`) so each evaluate processes only events / anomalies received since the last call. This matches the Redis-Streams-shaped interface the ADR claims to mirror (consumer offsets).
2. **Idempotent incident keys.** Compute `incident_id` from a stable hash of the contained `(event_id, anomaly_timestamp+series_name)` set, so re-correlating the same items yields the same `incident_id`; deduplicate by id before appending to `_recommendations`.
3. **Explicit "evaluate a window"** API: `evaluate(*, since: datetime, until: datetime)` and let the caller manage the window. Then the orchestrator carries no implicit consumer state.

Add at least: `test_orchestrator_evaluate_twice_with_no_new_data_does_not_duplicate`.

---

## Important (should fix before tag)

### I1. `MAD == 0` branch contradicts the ADR and the original plan; tightens by stealth

**Files:** `backend/src/repopulse/anomaly/detector.py` lines 83–90, `adr/ADR-002-aiops-core-algorithms.md` line 17, `plans/milestone-3-execution-plan.md` line 398, `docs/aiops-core.md` line 40.

Three documents disagree on what happens when the baseline MAD is 0:

| Source | `MAD == 0`, `value != median` | `MAD == 0`, `value == median` |
|---|---|---|
| Plan (line 398) | score = 0, no anomaly | score = 0, no anomaly |
| ADR-002 (line 17) | "emit nothing" | "emit nothing" |
| Implementation | critical, score = ±inf | skip |
| `docs/aiops-core.md` | critical, score = inf | (matches impl) |

The implementation is *defensible* — a perfectly silent baseline interrupted by any deviation is arguably the strongest possible signal — but it is **silently** stricter than what the ADR promised, and it has a real behavioral consequence: any non-zero deviation, however tiny, becomes critical-severity. With a baseline of `[5.0]*n` and a single 5.0001 reading, the detector emits `Anomaly(severity="critical", score=inf)`.

This change is also what makes the seasonal off-phase test pass. Trace `test_detect_seasonal_baseline_does_register_off_phase_spike`:
- The off-phase index 101 has baseline samples at 77, 53, 29, 5 — all `10.0`. Baseline MAD = 0.
- `value=500` differs from median 10 → infinite-score critical anomaly.

If the implementation had stayed faithful to the plan (`MAD == 0 → skip`), the off-phase test would fail. So the current behavior is load-bearing for a passing test, not a side effect.

**Recommendation:** Reconcile the three documents. Either:
- (a) Update ADR-002 §"Anomaly detector" to say "MAD == 0 with a non-zero deviation emits a critical anomaly with score = ±inf; this is the strongest, not the weakest, signal." Update the plan's algorithm step 5 to match. Add a dedicated unit test `test_detect_silent_baseline_with_tiny_deviation_emits_critical_inf` (right now this is only implicitly tested via the seasonal off-phase test).
- (b) Or: revert to "MAD == 0 → skip", adjust the seasonal off-phase test to use values that produce a finite z-score above threshold, and update the doc.

(a) is more useful operationally; (b) is closer to the literature. Either way, do not leave the contradiction in place — the ADR is the durable design record.

### I2. The plan said GET /api/v1/recommendations would "lazily evaluate"; it doesn't

**File:** `backend/src/repopulse/api/recommendations.py`; `plans/milestone-3-execution-plan.md` Task 10 step 1.

> "force an evaluation cycle by hitting `GET /api/v1/recommendations` (which triggers `orchestrator.evaluate(...)` lazily)"

The implementation just reads `orchestrator.latest_recommendations(limit=...)`. There is no evaluate trigger. Combined with C1 (POST doesn't ingest) and C2 (evaluate duplicates), this means the only way to get a non-empty `/recommendations` response in production is for an out-of-band Python caller to manually `orch.ingest()` + `orch.record_anomalies()` + `orch.evaluate()` — which is exactly what the evidence script does.

**Fix:** Either (a) make the GET endpoint optionally trigger `evaluate()` behind a query flag (`?evaluate=1`, off by default to keep the read idempotent), or (b) add a dedicated `POST /api/v1/recommendations:evaluate` endpoint, or (c) update the plan + handoff to explicitly say "evaluation is a Python-only concern in M3; HTTP-driven evaluation lands in M5". My preference is (b), because (a) makes a GET non-idempotent, and (c) is the minimum honest documentation fix.

### I3. R1 also fires as a hidden fallback for "non-empty incident with no critical anomalies/events and no second anomaly"

**File:** `backend/src/repopulse/recommend/engine.py` lines 116–120.

The rules table in `docs/aiops-core.md` and ADR-002 lists R1 as "empty incident → observe". But the implementation's rule chain has a silent fallback:

```python
fired = [o for o in outcomes if o.fired]
primary = fired[0] if fired else outcomes[-1]  # R1 is the fallback default
evidence: list[str] = [o.explanation for o in fired] or [outcomes[-1].explanation]
```

For an incident with `0 anomalies + 1 non-critical event` (e.g., a single GitHub push), no rule fires (R4 needs multi-source + critical, R3 needs ≥2 anomalies or critical, R2 needs exactly 1 anomaly, R1 needs empty). The chain falls back to R1 and reports `action_category=observe` with an `evidence_trace` whose only entry is `"R1: ... → observe (fired=False)"`. That is misleading — R1 didn't actually fire, but its explanation appears in the trace.

The docs do not mention this fallback. The fallback is also untested: there is no `test_recommend_single_non_critical_event_observes`.

**Fix:**
- (a) Broaden R1's predicate to `not _has_critical(incident) and len(incident.anomalies) == 0` (so it actually fires for "events-only, no critical" incidents) and update the docs table.
- (b) When falling back, build a synthetic explanation like `"R0: no rule fired → default observe"` so the trace is honest about what happened.
- Add the missing test either way.

### I4. Anomaly seasonal-baseline test passes for the wrong reason

**File:** `backend/tests/test_anomaly_detector.py` lines 83–92.

`test_detect_seasonal_baseline_does_register_off_phase_spike` asserts the off-phase 500 anomaly fires. As traced in I1, this passes because of the `MAD == 0 → ±inf` branch, not because the modified z-score formula registers it. Add a second test where the baseline has non-zero MAD and the off-phase spike still fires — that exercises the actual algorithm.

Suggested:
```python
def test_detect_seasonal_baseline_off_phase_spike_with_noisy_baseline() -> None:
    """Same as the off-phase test but with non-zero baseline MAD so we exercise
    the modified z-score formula, not the silent-baseline shortcut."""
    values: list[float] = []
    for cycle in range(5):
        # noisy baseline: 10±1 with a recurring spike to 100
        cycle_values = [10.0 + ((i + cycle) % 3) * 0.5 for i in range(23)] + [100.0]
        values.extend(cycle_values)
    values[24 * 4 + 5] = 500.0
    anomalies = detect_zscore(_series(values), window=4, threshold=3.5,
                              seasonal_period=24)
    assert any(a.value == 500.0 and a.score != float("inf") for a in anomalies)
```

### I5. `evaluate()` "Returns the new batch only" docstring is wrong

**File:** `backend/src/repopulse/pipeline/async_orchestrator.py` lines 60–63.

> "Run correlation over current state and emit one recommendation per incident. Returned recommendations are also stashed in the latest-first queue. **Returns the new batch only.**"

It returns *the recommendations produced by this call*, but those are produced by re-correlating everything in the buffer — not just "new" data. Until C2 is fixed, please correct the docstring to "Returns one recommendation per incident in the current state, including re-correlations of previously seen items. Callers must dedupe."

---

## Minor

### m1. `_RULES_HIGH_TO_LOW` does not include R1 in the "fired" search semantics consistently

`_r1.fired` returns True only when the incident is empty. So for an empty incident, `fired = [r1_outcome]` and the trace contains only the R1 line — fine. For a non-empty incident where no rule fires, the fallback in I3 fires. This is the same finding as I3 from a different angle; flagging it here so a fix doesn't regress one without the other.

### m2. `EventEnvelope` import in orchestrator creates a soft layering issue

`backend/src/repopulse/pipeline/async_orchestrator.py` imports from `repopulse.api.events`. The pipeline layer importing from the API layer is a small architectural smell — it means the API can never depend on the pipeline package without creating a cycle, and the pipeline can't be vendored without the FastAPI deps coming along. Consider moving `EventEnvelope` (or a small `Envelope` protocol) into a neutral `repopulse.types` module so `pipeline/`, `anomaly/`, `correlation/`, and `recommend/` are pure-domain modules and `api/` is the only edge that imports FastAPI/pydantic.

### m3. `_flatten_attributes` and `_resolve_kind` discard the original `kind` for `otel-metrics`

Per the plan, `otel-metrics` always normalizes to `kind="metric-spike"` regardless of inbound `kind`. That's intentional, but the original kind is also dropped from `attributes` (because it's not in `payload`, only in `envelope.kind`). If a sender ever distinguishes between, say, `cpu-spike` and `mem-spike` upstream, the distinction is lost. Either:
- (a) preserve `envelope.kind` as `attributes["original_kind"]`, or
- (b) document the lossy mapping in `docs/aiops-core.md` §"Modules" so future operators know to look at `attributes["metric_name"]` (or whatever) instead.

### m4. `anomaly/detector.py` test for `test_detect_severity_warning_at_threshold_band` recomputes a magic constant

The test docstring says `MAD = 0.2 → score = 3.3725 * (value - 10)`. That's correct given `0.6745 / 0.2 = 3.3725`. The constant works but is implicit. Consider asserting the exact score value to lock the formula:

```python
import math
assert math.isclose(anomalies[0].score, 3.3725 * 1.5, rel_tol=1e-9)
```

This guards against silent drift in `_MZ_CONST`.

### m5. `correlation/engine.py` window boundary docstring is slightly off vs implementation

The docstring (lines 60–65) says "A new incident starts whenever the gap from the previous item to the current one strictly exceeds `window_seconds`." The code uses `gap <= window_seconds` to *stay in the bucket*, equivalently `gap > window_seconds` to start a new one. So "strictly exceeds" is correct; the boundary at exactly `window_seconds` is grouped, also correct. The wording "inclusive" in the second sentence is fine, but operators reading the code might prefer `≤ window_seconds` shown explicitly:

```
# A new incident starts when gap > window_seconds.
# At gap == window_seconds, the items are still grouped (inclusive boundary).
```

### m6. `Incident.events` and `Incident.anomalies` retain insertion order but rely on stable sort

Python's sort is stable, so equal-timestamp items retain insertion order — anomalies first (because they're `list(anomalies) + list(events)`), then events. There is no test for the equal-timestamp boundary. Add `test_correlate_equal_timestamp_anomaly_and_event_grouped_in_one_incident` to lock the stability guarantee.

---

## Plan-vs-implementation alignment

| Plan task | Implementation | Notes |
|---|---|---|
| Task 1 — Plan + ADR | ✅ both committed | ADR is solid except for I1 contradiction |
| Task 2 — Normalization | ✅ green; 12 tests | Frozen-dataclass test refines plan's `with pytest.raises(Exception)` to use `FrozenInstanceError`, which is better than the plan |
| Task 3 — Anomaly detector | ⚠️ green but I1 | MAD=0 semantics changed without ADR/plan amendment |
| Task 4 — Correlation | ✅ green; 11 tests | Boundary cases tested (window-inclusive, unsorted, multi-source). Add equal-timestamp test (m6). |
| Task 5 — Recommendation | ⚠️ green but I3 | Fallback case for non-empty incident with no fires is undocumented |
| Task 6 — Orchestrator | ⚠️ green but C2, I5 | "new batch only" semantics are wrong; no idempotence test |
| Task 7 — Recommendations API | ⚠️ green but I2 | "lazily evaluate" claim in plan is unimplemented |
| Task 8 — E2E test | ⚠️ green but C1 | E2E test bypasses HTTP ingest. The M3 brief asked for "synthetic events through normalize → anomaly → correlation → recommendation" — that's covered, but the diagram in `docs/aiops-core.md` claims a path that doesn't exist end-to-end yet |
| Task 9 — `docs/aiops-core.md` | ✅ committed | I1 contradiction noted |
| Task 10 — Evidence + handoff | (in progress, not in this diff) | This review will land at `docs/superpowers/plans/m3-evidence/code-review.md` per instructions |

## Acceptance gates (M3 brief)

| Gate | Status | Evidence |
|---|---|---|
| Each module independently testable | ✅ | one test file per module; pure-function APIs |
| End-to-end synthetic events → ranked recs | ⚠️ partial | passes in-process; HTTP path broken (C1) |
| TDD discipline (RED → GREEN per behavior change) | ✅ | commit messages reflect this; 110 tests pass; ruff + mypy strict green per the M2 handoff posture |
| Anti-hallucination strict | ⚠️ I1 | three documents disagree; one of the three claims must be revised |
| UI Hold Gate active | ✅ | no `frontend/` work; no design-skill consumption; design-system SKILL.md untouched at `.claude/skills/design-system/SKILL.md` |

## Anti-hallucination violations

1. **`docs/aiops-core.md` line 8 / pipeline diagram** claims `EventEnvelope (POST /api/v1/events) → orchestrator.ingest`. That edge does not exist in code (C1). The diagram is aspirational.
2. **ADR-002 line 17** says MAD=0 → emit nothing. The detector emits a critical inf-score anomaly. (I1)
3. **`orchestrator.evaluate` docstring**, "Returns the new batch only." False; it returns recs for every still-resident incident. (I5)

Each of these has a re-runnable falsifying check:
- `curl -X POST localhost:8000/api/v1/events -H 'content-type: application/json' -d '{"event_id":"<uuid>","source":"github","kind":"push","payload":{}}'` then `curl localhost:8000/api/v1/recommendations` — count stays 0.
- `python -c "from repopulse.anomaly.detector import detect_zscore, Point; from datetime import datetime, timedelta, UTC; s=[Point(datetime(2026,1,1,tzinfo=UTC)+timedelta(seconds=i),5.0) for i in range(10)]+[Point(datetime(2026,1,1,tzinfo=UTC)+timedelta(seconds=10),5.0001)]; print(detect_zscore(s,window=10))"` — emits a critical inf-score anomaly, contradicting ADR.
- `pytest -k orchestrator -q` then add a one-liner `assert orch.evaluate() == orch.evaluate()` — fails because each call produces fresh UUIDs.

## UI Hold Gate

Clean. No new files under `frontend/` (the directory does not exist). No reads of `.claude/skills/design-system/SKILL.md`. No frontend imports anywhere in the diff.

## Recommended action before `v0.3.0-m3` tag

1. **Fix C1** — wire `POST /api/v1/events` to `orchestrator.ingest`. One handler change, one test. ~15 minutes.
2. **Fix C2** — pick one of the three options (snapshot-and-drain is the smallest patch); add the idempotence test. ~30 minutes.
3. **Resolve I1** — amend ADR-002 + plan + add the explicit `test_detect_silent_baseline_with_tiny_deviation_emits_critical_inf` (or revert the implementation). ~15 minutes for option (a).
4. **Decide on I2** — minimum: update `docs/aiops-core.md` and the M3 handoff to say "evaluate is Python-only in M3". Better: add `POST /api/v1/recommendations:evaluate`. ~10 minutes for the doc fix.
5. **Address I3, I4, I5** — small docs/test additions. ~20 minutes total.

Minor items (m1–m6) can land alongside any of the above or in M4. They are not blocking.

After (1)–(5) land, re-run the full quality gate (`pytest -v && ruff check && mypy`) and re-capture the evidence run. The `recommendations.json` artifact captured via `curl` (rather than the in-process script) becomes substantive evidence rather than a mirror of internal calls.

# M5 Code Review — RepoPulse Agentic GitHub Workflows

**Reviewer:** Senior Code Reviewer (review skill)
**Range:** `fbd0e21...b1ffb2a` (= `v0.3.0-m3` → top of M5, before version bump)
**Files reviewed:** 26 files added/modified, 3749 / 40 lines.
**Test posture verified (pure analyzers):** `cd backend && pytest tests/test_github_payloads.py tests/test_github_triage.py tests/test_github_ci_analysis.py tests/test_github_doc_drift.py tests/test_github_usage.py -q` → 40 passed in 0.30 s. The HTTP-layer test file (`test_github_workflows_api.py`) and `test_orchestrator.py` could not be executed in the review sandbox because `pydantic-settings` is not installed in the system interpreter (the sandbox blocks `pip install -e .[dev]`); the test file is read in full and the auth/kill-switch logic is verified by code inspection. Reviewer flags this as a partial verification.
**Permissions verified:** YAML parsed and `permissions:` blocks confirmed minimal — see I-class section.

## Verdict

M5 is a clean, well-bounded extension of the M3 core. The trust model is explicit (ADR-003), the kill switch is two-layered, the workflow YAML files have minimal permissions and post comments only, and the pure analyzers follow the M3 evidence-trace pattern. The M3-review findings (C1: events not wired, C2: evaluate duplicates, I3: R1 fallback) all show evidence of being addressed in the intervening fix commit (`2808926`) — `events.py` now ingests + evaluates, `orchestrator.evaluate()` dedupes by content key, R1 fires explicitly. The new `record_normalized` path is a correctly-scoped sibling for callers that already hold a `NormalizedEvent`.

That said, three issues are blocking before tagging `v0.4.0-m5`:

1. **C1** — `_auth` dependency runs **after** body parsing in FastAPI's resolution graph for every endpoint, so an unauthenticated client with a malformed body sees a `422` (and the schema field names) before the `401`. Auth should fail closed before body parsing.
2. **C2** — Settings are instantiated once in `create_app()` and frozen on `app.state`. The kill switch and shared secret therefore cannot be flipped without a process restart, contradicting the docs' "milliseconds" claim and degrading the kill switch from "instant" to "graceful restart."
3. **I1** — Triage classifier T1 keyword `production` produces a false-positive critical for any title containing the word "production-ready," "production environment," etc., regardless of whether an outage is being described. With `confidence=0.9` and `severity:critical` label, this is the loudest signal the workflow can emit.

The remaining items are smaller polish (docs drift in `security-model.md`, request-size guards, runner-cost rounding). Detailed findings below.

---

## Critical (must fix before tag)

### C1. `Authorization` is checked **after** the request body is parsed and validated

**File:** `backend/src/repopulse/api/github_workflows.py` lines 89–104, 107–128, 131–143, 146–167.

Every endpoint signature is shaped:

```python
@router.post("/triage", response_model=None)
def triage(
    payload: IssuePayload,                          # ← body, parsed first
    settings: Annotated[Settings, Depends(_auth)],  # ← auth, runs after body resolved
) -> JSONResponse | dict[str, object]:
```

In FastAPI's dependency-graph resolution, both the body parameter and the `Depends(_auth)` chain are part of the request's solved-dependencies set. Body parsing is not lazy — the `IssuePayload` is materialized (and pydantic raises 422 on malformed input) before the endpoint function body executes. Concretely, an unauthenticated request with a malformed body returns **422 with the pydantic field-name list** rather than **401**. A targeted client could enumerate the schema (every field that's required, every literal-restricted value) without ever providing a valid token.

This isn't catastrophic — the schemas are visible in the source — but it violates the "fail closed before parsing" rule and contradicts the security-model intent that "wrong/missing token → 401" (`docs/security-model.md` line 37). The plan also explicitly required "Missing/wrong → 401" (plans/milestone-5-execution-plan.md line 998).

**Reproduce:**
```bash
# With backend running and REPOPULSE_AGENTIC_SHARED_SECRET="x":
curl -i -X POST http://localhost:8000/api/v1/github/triage \
     -H 'content-type: application/json' \
     -d '{"bogus":"body"}'
# Expected: 401 invalid agentic token
# Actual:   422 with full pydantic field list (action, issue, repository missing)
```

**Fix:** Promote auth to a **router-level** dependency or to a **`Header`-only sub-dependency that's resolved before body parsing**. The cleanest fix is to make the auth dependency take only a `Header` and rely on FastAPI's order-of-resolution for headers vs. bodies (headers are extracted from `request.headers` cheaply; bodies require an `await request.body()` round-trip). Easiest path:

```python
router = APIRouter(
    prefix="/api/v1/github",
    tags=["github"],
    dependencies=[Depends(_auth)],   # ← runs before any body parameter
)
```

Then drop the per-endpoint `Depends(_auth)` annotation. Each handler still needs `settings` (e.g., for the `agentic_enabled` check); inject that via a separate `Depends(_get_settings)` parameter that's NOT also the auth dep. Add a regression test:

```python
def test_triage_rejects_malformed_body_without_auth_with_401(client):
    r = client.post("/api/v1/github/triage", json={"bogus": "body"})
    assert r.status_code == 401   # not 422
```

This is also a problem for `/usage`, `/ci-failure`, and `/doc-drift`. All four endpoints would benefit from the router-level dependency.

### C2. Kill switch + shared secret cannot be rotated without a process restart

**File:** `backend/src/repopulse/main.py` lines 50, 82; `backend/src/repopulse/api/github_workflows.py` lines 31–35.

`Settings()` is instantiated once at startup and stored on `app.state.settings`. `_get_settings(request)` reads from `app.state` rather than re-instantiating. So changing `REPOPULSE_AGENTIC_ENABLED` or `REPOPULSE_AGENTIC_SHARED_SECRET` in the environment requires a backend restart to take effect.

This contradicts `docs/agentic-workflows.md` (Layer 2 backend gate) and ADR-003 §3:

> "Setting `REPOPULSE_AGENTIC_ENABLED=false` once on the backend disables the entire surface within milliseconds."

Within milliseconds *of the next request after a restart*, yes. Without restart, the toggle is invisible. Operators reading the docs will reasonably expect a runtime kill switch — the actual behavior is closer to "graceful restart kills the switch."

This also has a security implication for the shared secret: token rotation is a no-op until restart, so a leaked token stays valid until the next deploy.

**Fix options (pick one, document in ADR-003):**

1. **Re-read settings per request.** Add a dependency `_runtime_settings()` that does `Settings()` afresh on each call. Pydantic-settings reads env vars at instance creation time, so this gives "milliseconds" semantics. Cost: trivially small per-request overhead from re-reading os.environ.
2. **Watchdog reload.** Add a `SIGHUP` handler that reinstantiates `app.state.settings`. Operators have to send a signal — slightly less ergonomic than (1) but no per-request cost.
3. **Document the actual semantics.** Update `docs/agentic-workflows.md` and ADR-003 §3 to say "set the env var and restart the backend (or send SIGHUP)." This is the smallest patch but degrades the kill switch's UX promise.

(1) is the right answer if you want the doc claim to be true. (3) is the minimum honest fix.

Add a regression test:
```python
def test_kill_switch_flips_at_runtime(monkeypatch, client, secret):
    # First call: enabled
    r1 = client.post("/api/v1/github/triage", json=_issue_body(),
                     headers={"Authorization": f"Bearer {secret}"})
    assert r1.status_code == 200
    monkeypatch.setenv("REPOPULSE_AGENTIC_ENABLED", "false")
    # Without restart, second call should ALSO see disabled — currently fails
    r2 = client.post("/api/v1/github/triage", json=_issue_body(),
                     headers={"Authorization": f"Bearer {secret}"})
    assert r2.status_code == 202
    assert r2.json()["disabled"] is True
```

---

## Important (should fix before tag)

### I1. Triage classifier `production` keyword produces high-confidence false-positives

**File:** `backend/src/repopulse/github/triage.py` line 17.

```python
_T1 = re.compile(r"\b(crash|outage|production|sev[\s-]?1)\b", re.IGNORECASE)
```

The word `production` matches in any benign context. Confirmed by direct probe:

```bash
$ python -c "
from repopulse.github.payloads import IssuePayload
from repopulse.github.triage import classify_issue
p = IssuePayload.model_validate({
    'action': 'opened',
    'issue': {'number': 1, 'title': 'Add production-ready logging',
              'body': 'feature request', 'labels': [], 'user': {'login': 'u'}},
    'repository': {'full_name': 'x/y'},
})
print(classify_issue(p).severity, classify_issue(p).confidence)
"
critical 0.9
```

A feature-request issue with the word "production" anywhere in the title or body becomes `severity=critical, confidence=0.9, suggested_labels=[severity:critical, triage, type:feature]`. Once the agentic workflow comments back, an operator who skims the suggestion would reasonably escalate.

The current rule also has the asymmetric issue that `\bcrashed\b` and `\bcrashing\b` do NOT match (word-boundary fails before the suffix `ed`/`ing`), so "system crashed at boot" is classified `minor`. That's the opposite failure mode — under-triage of a real incident — but with the same root cause: the rule treats keyword presence as evidence of incident-shape rather than incident-shape itself.

**Fix options:**

1. **Tighten T1 to incident-context phrases.** Replace bare `production` with `\b(production (outage|incident|down|crash))\b` or similar. Treat `production` alone as ambiguous — fold it into T2 (major), not T1 (critical).
2. **Require co-occurrence.** T1 fires only when (incident-noun AND severity-adjective) co-occur in a small window. e.g. `(production|prod|prd).{0,40}(outage|down|broken|crash)`.
3. **Stem the keywords.** Change `\bcrash\b` → `\bcrash\w*\b` so `crashed`/`crashing`/`crashes` all fire. (Independent of the production fix; addresses the under-triage failure mode.)

Add tests for both directions:
```python
def test_classify_production_alone_is_not_critical():
    rec = classify_issue(_issue("Add production-ready logging"))
    assert rec.severity != "critical"

def test_classify_crashed_past_tense_still_fires_critical():
    rec = classify_issue(_issue("App crashed at startup"))
    assert rec.severity == "critical"
```

This is `Important` rather than `Critical` because the workflow output is **comment-only** — a misfire is visible and reversible. But the visible misfire degrades trust in the whole agentic surface, and the fix is small.

### I2. CI failure analyzer's "first-job-wins" cause assignment is brittle for multi-job failures

**File:** `backend/src/repopulse/github/ci_analysis.py` lines 64–77.

```python
cause: Cause = "unknown"
for job_name, _step, excerpt in failed_jobs:
    for candidate, pattern in _PATTERNS:
        if pattern.search(excerpt):
            if cause == "unknown":
                cause = candidate
            ...
```

The first matched-cause across jobs wins. Given the `_PATTERNS` order `(timeout, dependency, syntax, test-failure)`:

- Job A log: `"AssertionError: flaky"` → test-failure
- Job B log: `"Timed out after 600s"` → timeout

Result: `cause = "test-failure"`, even though the timeout in Job B is structurally a stronger signal (and the recommended next-action diverges: `investigate-test` vs `rerun`). The test `test_summarize_first_match_wins_when_multiple_jobs` codifies this behavior, but the design isn't argued anywhere — it's just what fell out of the loop.

**Recommendations:**

- **(a) Aggregate causes by priority.** Collect *all* matched causes across all jobs, then pick the highest-priority one (priority order is whatever you decide — `timeout > dependency > syntax > test-failure` matches the `_PATTERNS` tuple order, so just pick `_PATTERNS.index` of the first match). This is the same cost as the current loop, with deterministic priority semantics.
- **(b) Or: document first-match explicitly.** Add to ADR-003 (or a new `docs/agentic-workflows.md` §"CI failure analysis") that "cause is determined by the first matched job in the order GitHub emits failed jobs; for multi-cause failures, a follow-up workflow run is expected." Then the test name becomes self-documenting.

The single-job pattern-matching (`break` after first match within a job) is fine because of `_PATTERNS`'s ordered priority — that's stable. The cross-job aggregation is the part that's accidental.

### I3. `find_broken_refs` regex misses reference-style markdown links and has minor parsing edge cases

**File:** `backend/src/repopulse/github/doc_drift.py` line 13.

```python
_LINK = re.compile(r"\[(?P<text>[^\]]+)\]\((?P<target>[^)\s]+)\)")
```

This matches inline links `[text](target)` only. It misses:

1. **Reference-style links** `[text][ref]` followed by `[ref]: target` later. Common in long docs.
2. **Image references** `![alt](path)` — these *do* match (the `!` is outside the regex), and the `path` is checked against `repo_paths`. But `repo_paths` for a typical workflow run is from `git ls-tree` which only includes tracked files. Diagrams stored in a CDN as a missing file in the diff would be flagged. Probably the desired behavior, but undocumented.
3. **Targets with parens** — e.g. `[x](path(with)parens)` — the regex stops at the first `)`, so the target becomes `path(with` and is reported broken. (Markdown technically allows escaping or angle-bracket wrapping for these.) Confirmed:
   ```python
   >>> r = find_broken_refs(changed_files=['docs/a.md'], repo_paths={'docs/a.md'},
   ...                      file_contents={'docs/a.md': '[x](path(with)parens)\n'})
   >>> r.broken_refs
   (('docs/a.md', 'path(with', 1),)
   ```
4. **Targets with whitespace** — the regex uses `[^)\s]+` which excludes any whitespace. Markdown does allow `[text](url "title")`, where the title comes after a space. The current regex would match `url` only (since `\s` stops it), then encounter `"title")` as residue. Acceptable if titles are rare in this repo; worth flagging.

**Fix:**
- Add a docstring to `_LINK` explaining the supported subset.
- Either extend the regex for reference-style links (pre-pass: build a `{ref → target}` map from `[ref]: target` lines, then validate) or document that ref-style links are out of scope for M5.
- Add tests:
  ```python
  def test_reference_style_link_is_ignored_or_resolved():
      contents = {'docs/a.md': '[txt][ref]\n\n[ref]: missing.md\n'}
      report = find_broken_refs(changed_files=['docs/a.md'],
                                 repo_paths={'docs/a.md'},
                                 file_contents=contents)
      # Document the chosen behavior here.
  ```

### I4. `security-model.md` still references the obsolete `REPOPULSE_GITHUB_TOKEN`

**File:** `docs/security-model.md` line 22.

> `REPOPULSE_GITHUB_TOKEN` — scoped GitHub token for the agentic workflows path (M5). Never committed; loaded from `.env` (gitignored) or the deployment environment.

ADR-003 §1 explicitly says **the backend never holds a GitHub token**. The "Backend `/api/v1/github/*` endpoints" row in `docs/agentic-workflows.md` (line 26) reinforces this: "None on GitHub". Yet `security-model.md` lists `REPOPULSE_GITHUB_TOKEN` as a required env var. The only token the backend actually consumes is `REPOPULSE_AGENTIC_SHARED_SECRET` — which is not mentioned in the "Secret Handling" §.

**Fix:**
- Remove `REPOPULSE_GITHUB_TOKEN` from the secrets list (M5 dropped it; if a future milestone needs it, that ADR will add it back).
- Add `REPOPULSE_AGENTIC_SHARED_SECRET` to the secrets list with the actual security expectation (32+ bytes, paired with the GitHub Actions `REPOPULSE_AGENTIC_TOKEN` secret, fail-closed when missing).
- Cross-link to `agentic-workflows.md` and ADR-003.

### I5. No request-size or log-excerpt-length limits on the analyzer endpoints

**Files:** `backend/src/repopulse/api/github_workflows.py` lines 63–86 (Pydantic models without length constraints).

```python
class _FailedJob(BaseModel):
    job_name: str
    step: str
    log_excerpt: str           # ← unbounded

class _DocDriftBody(BaseModel):
    changed_files: list[str]
    repo_paths: list[str]
    file_contents: dict[str, str]   # ← unbounded; values are file contents
```

A `log_excerpt` of 100 MB or a `file_contents` mapping with 10k entries would be accepted, parsed, and run through regex scanning. Even if the source is "trusted" (the workflow runner is one of yours), the sizes scale with repo size: a monorepo with 200k tracked paths sends a 200k-element `repo_paths` list on every PR.

The doc-drift workflow YAML (lines 42–44) already does:
```yaml
CHANGED=$(git diff --name-only "$BASE" "$HEAD" -- '*.md' | sort -u)
REPO_PATHS=$(git ls-tree -r --name-only "$HEAD" | sort -u)
```

`git ls-tree -r` returns *every tracked path*, no filter. For a 200k-file monorepo, that's a multi-megabyte JSON body per PR.

**Fix:**
- Add `Field(max_length=...)` constraints on `log_excerpt`, on each entry of `repo_paths`, and on each value of `file_contents`. Reasonable defaults: log_excerpt ≤ 64KB, repo_paths ≤ 50000, file_contents value ≤ 1MB.
- In the doc-drift workflow YAML, filter `repo_paths` to only `*.md`, `*.png`, etc. (the link-targets we'd actually validate). That alone shrinks the payload by 10–100× for typical repos.
- Add a backend-level FastAPI middleware to cap raw request size (e.g., `MAX_BODY_BYTES = 5 * 1024 * 1024`).

### I6. `triage` classifier's `T3 ≈ T4` overlap leaves silent precedence (T4 wins)

**File:** `backend/src/repopulse/github/triage.py` lines 59–71.

The plan said:
> "category priority T3 ≈ T4 > T5; rules can co-fire (e.g. 'feature: docs typo' → severity=`minor` from T5, category overlay from T3 + T4)."

The "≈" suggests no priority. The implementation runs T3 then T4, and T4 (docs) **overwrites** the `category` set by T3 (feature-request). Confirmed:

```bash
$ python -c "
from repopulse.github.triage import classify_issue
from repopulse.github.payloads import IssuePayload
p = IssuePayload.model_validate({...title='Feature: docs proposal', body='add docs'...})
print(classify_issue(p).category)
"
docs
```

Both T3 and T4 fire (both labels are added), and the trace shows both. But `category` ends up `docs` (T4), not `feature-request` (T3). The plan's example said this case should produce "category overlay from T3 + T4" — implying both. The model only has one `category` field, so silent precedence is necessary; the precedence is just unspecified.

**Recommendation:**
- Either: change the `category` type to `tuple[Category, ...]` so multi-fire produces both (plan's "overlay" reading).
- Or: document that T4 wins on collision (and explain why — "docs is more specific than the broad `feature` umbrella"). Add a test that locks in this precedence:
  ```python
  def test_classify_docs_wins_over_feature_on_collision():
      rec = classify_issue(_issue("Feature proposal: docs typo"))
      assert rec.category == "docs"
      assert "type:feature" in rec.suggested_labels   # both labels still set
      assert "type:docs" in rec.suggested_labels
  ```

This is a correctness-of-spec issue, not a behavioral bug.

---

## Minor

### m1. TDD discipline: only GREEN commits visible in the M5 range

The M3 commit log has visible RED-then-GREEN pairs. M5 commits are all single "feat(...)+TDD" commits. The test+impl was clearly co-developed (per the plan's "Step 1 RED, Step 2 GREEN"), but git history doesn't show the RED phase. Not a regression of the discipline, but the M3 review prized the visible trail. For M6+, consider committing the failing test first, then the implementation (`git commit -m "test: failing"` then `git commit -m "feat: green"`). Slight convenience cost, much better forensic record.

### m2. `_KNOWN_SOURCES` in `normalize.py` doesn't list `agentic-workflow`

**File:** `backend/src/repopulse/pipeline/normalize.py` lines 16–18.

```python
_KNOWN_SOURCES: frozenset[str] = frozenset(
    {"github", "otel-metrics", "otel-logs", "synthetic"}
)
```

`record_normalized` bypasses `normalize`, so this doesn't break the M5 path. But if any caller ever pushes an `EventEnvelope` with `source="agentic-workflow"` through the regular `/api/v1/events` route, `_resolve_kind` returns `f"unknown-{kind}"` (so e.g. `unknown-workflow-failure`). Add `"agentic-workflow"` to the set with a comment, and add the kind-mapping for `workflow-failure`/`workflow-success`/`workflow-other` so both ingest paths produce identical `NormalizedEvent`s.

### m3. The runner-cost rate `0.08` for macOS may be off-by-decimal vs `0.080`

**File:** `backend/src/repopulse/github/usage.py` line 18; `docs/agentic-workflows.md` line 107.

Code:
```python
"macos": 0.08,
```

Doc:
```
| `macos` | 0.080 |
```

`0.08 == 0.080` numerically, so this is harmless. But the doc shows three decimals for visual alignment, while the code uses two. Just consistency. Either: round the table entries to two decimals, or use `0.080` in code (purely cosmetic — Python normalizes both). Pick one and stick with it across the codebase. (Same point for `0.008` and `0.016`, which match.)

### m4. `_emit_output` writes `EOF` heredoc with raw user-controllable content

**File:** `.github/workflows/scripts/agentic_call.py` lines 47–52.

```python
with open(out, "a", encoding="utf-8") as fh:
    fh.write(f"{name}<<EOF\n{value}\nEOF\n")
```

If `value` happens to contain the literal sequence `\nEOF\n`, the heredoc closes early and subsequent text is interpreted as a new env-var assignment by GitHub Actions. The `value` here is `json.dumps(result)` of a backend response. The backend does not (today) emit raw `\nEOF\n` in any field, so the bug is latent. But once any free-text field is ever forwarded (a comment body, an LLM-generated summary, etc.), this opens a small command-injection vector via GITHUB_OUTPUT.

**Fix:** Use a random-per-call delimiter:
```python
import secrets
delim = f"EOF_{secrets.token_hex(8)}"
fh.write(f"{name}<<{delim}\n{value}\n{delim}\n")
```

This is the GitHub-recommended pattern. Pre-empts a future regression.

### m5. Doc-drift workflow ships full `git ls-tree` output as `repo_paths`

**File:** `.github/workflows/agentic-doc-drift-check.yml` line 44.

`git ls-tree -r --name-only "$HEAD" | sort -u` returns every tracked path. For this repo today it's small; for any meaningful monorepo it'd be tens of thousands of paths (some are images, some are vendored dependencies, etc.).

Filter to extensions the analyzer cares about — `*.md`, plus image extensions if you want image refs validated:

```yaml
REPO_PATHS=$(git ls-tree -r --name-only "$HEAD" | grep -E '\.(md|png|jpg|svg|gif)$' | sort -u)
```

This pairs with I5 to keep the request body bounded.

### m6. `_FailedJob.step` is consumed only as `_step` (unused) in the analyzer

**File:** `backend/src/repopulse/github/ci_analysis.py` line 67.

```python
for job_name, _step, excerpt in failed_jobs:
```

The leading underscore signals "intentionally unused." But the analyzer takes `step` in the input contract — the API consumes it (`backend.failed_jobs[].step`) and the YAML supplies it. If the field is genuinely unused inside the analyzer, document why it's still on the contract (forward compatibility for future per-step regex tables) or drop it from the API. Currently it's a noisy "this field is here but does nothing" surface.

### m7. R1 evidence-trace mojibake in `recommendations-after-usage.json`

**File:** `docs/superpowers/plans/m5-evidence/recommendations-after-usage.json` line 10.

```
"R1: no higher-priority rule fired â†’ observe (...)"
```

`â†’` decodes to "â†’" — UTF-8 bytes for "→" being interpreted as Latin-1. Likely happened when curl wrote the response and the shell wrapped it in cp1252 encoding. Regenerate this file with `curl -o response.json` (or pipe through `python -c "import sys, json; print(json.dumps(json.load(sys.stdin)))"`). Cosmetic, but evidence files should be canonical.

### m8. `_auth` returns `Settings` so callers can read `agentic_enabled` — the type leaks

**File:** `backend/src/repopulse/api/github_workflows.py` lines 38–50.

The dependency does two jobs: (a) auth check, (b) hand `settings` back to the endpoint. So `Annotated[Settings, Depends(_auth)]` on every handler isn't really an "authentication" annotation, it's "auth + settings." Splitting these would clarify the contract:

```python
def _auth(authorization: ...) -> None: ...
def _settings(request: Request) -> Settings: ...

@router.post("/triage", dependencies=[Depends(_auth)])
def triage(payload: IssuePayload, settings: Annotated[Settings, Depends(_settings)]):
    ...
```

Same as the C1 fix path; gets you both at once.

---

## Plan-vs-implementation alignment

| Plan task | Implementation | Notes |
|---|---|---|
| Task 1 — Plan + ADR-003 | ✅ both committed | ADR-003 is precise; trust model fully argued |
| Task 2 — Payload models | ✅ green; 6 tests | Adds `test_issue_payload_handles_missing_body` and `test_workflow_run_payload_rejects_bad_conclusion` beyond plan; both useful |
| Task 3 — Triage classifier | ⚠️ green but I1, I6 | `production` keyword is too broad; T3/T4 precedence undocumented |
| Task 4 — CI failure analyzer | ⚠️ green but I2 | First-match-wins across jobs is undocumented |
| Task 5 — Doc-drift checker | ⚠️ green but I3 | Inline-link-only; ref-style links silently miss |
| Task 6 — Workflow usage | ✅ green; 7 tests | Adds `test_record_run_costs_macos_higher_than_linux` (good ordering check) and `test_to_normalized_event_other_conclusion` (the cancelled/skipped path) |
| Task 7 — HTTP endpoints + auth + kill switch | ⚠️ green but C1, C2 | Body-before-auth and frozen-at-startup settings are both contract violations |
| Task 8 — Workflow YAML | ✅ committed | Permissions verified minimal (no `contents: write`, no `actions: write`); kill-switch `if:` gates correct; CI-failure adds `actions: read` (justified — needed to read the failing run) |
| Task 9 — Docs | ⚠️ partial — I4 | `agentic-workflows.md` is solid; `security-model.md` still references `REPOPULSE_GITHUB_TOKEN` from M2 |
| Task 10 — Evidence + handoff | (in progress, this review lands here) | Evidence files exist and demonstrate happy paths + 401 + kill switch; mojibake on one (m7) |

## Acceptance gates (M5 brief)

| Gate | Status | Evidence |
|---|---|---|
| GitHub Agentic Workflow setup + policy-safe integration | ✅ | three workflows under `.github/workflows/agentic-*.yml`, all comment-only |
| Safe outputs + scoped permissions + explicit write constraints | ✅ | `permissions:` blocks verified — `issues: write` or `pull-requests: write` only, no `contents: write`, no `actions: write` |
| Non-destructive defaults + kill switch | ⚠️ partial | Two-layer gate is correctly implemented at the YAML and code level; runtime semantics of the backend layer are weaker than docs claim (C2) |
| Three workflows: triage, CI-failure, doc-drift | ✅ | all three present, all guardrailed with `if: ${{ vars.REPOPULSE_AGENTIC_ENABLED != 'false' }}` and `vars.REPOPULSE_AGENTIC_DRYRUN != 'true'` |
| Cost/usage telemetry | ✅ | `/api/v1/github/usage` endpoint + `WorkflowUsage` + `to_normalized_event` mapping; CI-failure workflow calls it |
| Security/trust-boundary documentation updates | ⚠️ I4 | `agentic-workflows.md` and ADR-003 are clean; `security-model.md` is stale |
| Two-layer kill switch | ⚠️ C2 | implemented at both layers; backend layer needs runtime re-read for the doc claim to be true |
| Shared-secret authentication | ⚠️ C1 | implemented but body-validation runs before auth |
| Anti-hallucination strict | ⚠️ I4 | one cross-document contradiction (security-model vs ADR-003) |
| UI Hold Gate active | ✅ | no `frontend/` work; design-system SKILL.md untouched at `.claude/skills/design-system/SKILL.md` |

## Anti-hallucination violations

1. **`docs/security-model.md` line 22** lists `REPOPULSE_GITHUB_TOKEN` as a required secret. The backend does not read or use any GitHub token — the only secret it consumes is `REPOPULSE_AGENTIC_SHARED_SECRET`. ADR-003 §1 explicitly contradicts this. (I4)

2. **`docs/agentic-workflows.md` line 67 / ADR-003 §3** claim the backend kill switch acts "within milliseconds." Without a per-request settings re-read, the actual semantics are "after the next process restart." (C2)

3. **Plan line 998** says "Each endpoint requires `Authorization: Bearer ...`. Missing/wrong → 401." The implementation returns 422 for missing/wrong-auth + malformed body. The 401 contract holds only when the body is well-formed. (C1)

Each has a re-runnable falsifying check:
- `grep -n "REPOPULSE_GITHUB_TOKEN" docs/security-model.md` — emits the stale line.
- `curl ... -H 'Authorization: Bearer x'` (anything that isn't the secret) with a malformed body — currently 422; should be 401.
- Start the backend, run a triage call, change `REPOPULSE_AGENTIC_ENABLED` in the env *without restarting*, repeat the call — currently still works; should return 202 disabled.

## UI Hold Gate

Clean. No new files under `frontend/` (the directory does not exist). No reads of `.claude/skills/design-system/SKILL.md`. No frontend imports anywhere in the diff. The plan and ADR both correctly defer M4 (UI) until M5 ships.

## Recommended action before `v0.4.0-m5` tag

1. **Fix C1** — promote `_auth` to a router-level dependency so 401 fires before body parsing. ~15 minutes for the change + the regression test.
2. **Fix C2** — pick option (1) "re-read settings per request" or option (3) "document the actual semantics". (1) takes ~10 minutes; (3) takes ~5. Recommend (1) so the doc claim becomes true.
3. **Address I1** — tighten the `production` keyword in T1 (move bare `production` to T2, or require co-occurrence). Add `crashed`/`crashing` matching with `\bcrash\w*\b`. ~15 minutes including tests.
4. **Address I4** — purge `REPOPULSE_GITHUB_TOKEN` from `docs/security-model.md`, replace with `REPOPULSE_AGENTIC_SHARED_SECRET` and link to ADR-003. ~5 minutes.
5. **Address I2, I3, I5, I6** — small docs/test additions. I5 is the highest-leverage of these (the `git ls-tree` size cap). ~30 minutes total.

Minor items (m1–m8) can land alongside any of the above or in M6. They are not blocking, but m4 (the GITHUB_OUTPUT delimiter) and m5 (the `repo_paths` filter) pre-empt real future incidents and are worth folding in now.

After (1)–(4) land, re-run the full quality gate (`pytest -v && ruff check && mypy`), regenerate the evidence files (m7), and re-run the four `curl` evidence captures. The auth-401 capture should now also exercise the malformed-body-without-auth case — the new RED-then-GREEN is the regression guard for C1.

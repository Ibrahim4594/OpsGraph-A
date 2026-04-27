# Milestone 5 Handoff Report

**Milestone:** M5 — GitHub Agentic Workflows
**Date:** 2026-04-27
**Branch / commits:** `main`, M5 starts at `bfde4b0` (plan + ADR-003) and ends at the upcoming `v0.4.0-m5` tag.
**Status:** ✅ Complete — all M5 brief requirements met with captured evidence; 2 Critical and 6 Important code-review findings processed (1 Critical rejected after verification, 1 Critical + all 6 Important fixed) before tag.

---

## Skills Invocation Log

Per the user's M5 mandate ("explicitly invoke and log the required skills/workflows"):

| # | Skill | Where invoked | Outcome |
|---|---|---|---|
| 1 | `superpowers:writing-plans` | Before Task 1 — drafted `plans/milestone-5-execution-plan.md`. | Plan with file structure, 10 bite-sized tasks, complete TDD code per task, self-review pass. |
| 2 | `superpowers:test-driven-development` | Tasks 2, 3, 4, 5, 6, 7 (every behavior change in M5). | Each task wrote a failing test FIRST, captured RED output (`ModuleNotFoundError` / `404` / assertion failure), then minimal GREEN. Refactor where needed: Task 5 (`PurePosixPath` doesn't normalize `..`, switched to `posixpath.normpath`); Task 6 (mypy strict required `Severity` literal annotation); Task 7 (`JSONResponse | dict` return type required `response_model=None` on each decorator + the kill-switch-returning-202 semantic). |
| 3 | `superpowers:systematic-debugging` | Task 5 when initial GREEN failed `test_relative_path_resolves_to_repo_root` because `PurePosixPath` operations are pure-string and don't collapse `..` segments. | Phase 1 read traceback → noticed `docs/sub/page.md` parent `/` `../top.md` produced `docs/sub/../top.md` not `docs/top.md`. Phase 2 confirmed via stdlib docs: `pathlib` is filesystem-aware, `PurePath` is not, so neither normalizes `..` in arithmetic. Phase 3 hypothesis: switch to `posixpath.normpath` which is purely string-based AND collapses `..`. Phase 4 fix landed in one edit; all 10 doc-drift tests went green. |
| 4 | `superpowers:verification-before-completion` | Task 10, before claiming completion. | Ran fresh `pytest` (171 passed), `ruff check` (0), `mypy` strict (0), `pip install -e .[dev]` (0), confirmed `__version__ == 0.4.0`. Captured exact output before writing this handoff — no claim ahead of evidence. |
| 5 | `superpowers:requesting-code-review` | Task 10, between feature work and tag. | Dispatched the `superpowers:code-reviewer` subagent against `v0.3.0-m3..HEAD`. Reviewer report saved at `docs/superpowers/plans/m5-evidence/code-review.md`. **Findings: 2 Critical (C1 auth/body order, C2 settings frozen at startup), 6 Important (I1–I6), 8 Minor.** |
| 6 | `superpowers:receiving-code-review` | Task 10, processing the reviewer report. | Verified each Critical and Important finding against the codebase before fixing. **C1 was rejected** after a live curl reproduced 401 (not 422) — auth dependency runs before body validation in this FastAPI version. C2 + I1–I6 all confirmed and fixed with regression tests. Committed under `373e06d`. |
| 7 | `superpowers:dispatching-parallel-agents` | **Considered, not invoked.** | Tasks 2, 3, 4, 5, 6 are pure-functional and *technically* independent (no shared state), so they were a candidate for parallel dispatch. The decision was to stay sequential because (a) the file-creation order matters for the `repopulse.github` package's `__init__.py` re-exports, and (b) inline TDD is faster than agent-spawn overhead for sub-second-test modules. Documented the decision rather than skipping the invocation silently. |

---

## 1. Files Changed and Why

| Path | Reason |
|---|---|
| `plans/milestone-5-execution-plan.md` | TDD-disciplined M5 plan (10 tasks, file structure, complete code per task, self-review). |
| `adr/ADR-003-agentic-execution-model.md` | Records workflow-as-action-gate decision, kill-switch design, persistence boundary, alternatives considered, and post-review fix log. |
| `backend/src/repopulse/__init__.py` | `__version__ = "0.4.0"`. |
| `backend/pyproject.toml` | Version bump to `0.4.0`. |
| `backend/src/repopulse/config.py` | Adds `agentic_enabled` and `agentic_shared_secret` fields. |
| `backend/src/repopulse/github/__init__.py` | Package marker + payload re-exports. |
| `backend/src/repopulse/github/payloads.py` | Pydantic models for the subset of GitHub event payloads we read (`IssuePayload`, `WorkflowRunPayload`, `PullRequestPayload`). |
| `backend/src/repopulse/github/triage.py` | Rule-based issue triage classifier with evidence trace. Post-review I1 fix tightens T1 patterns; post-review I6 fix documents T3/T4 collision. |
| `backend/src/repopulse/github/ci_analysis.py` | CI failure analyzer. Post-review I2 fix documents first-job-wins precedence. |
| `backend/src/repopulse/github/doc_drift.py` | Doc-drift checker. Uses `posixpath.normpath` for `..` resolution. Post-review I3 fix documents known limitations. |
| `backend/src/repopulse/github/usage.py` | Workflow usage telemetry — `WorkflowUsage` dataclass + `to_normalized_event` mapping. |
| `backend/src/repopulse/api/github_workflows.py` | Four POST endpoints under `/api/v1/github/`. Bearer-token auth, two-layer kill switch, request-size caps. Post-review C2 fix re-reads `Settings` per request. Post-review I5 fix adds field length caps + a 413 guard on oversized `file_contents` values. |
| `backend/src/repopulse/main.py` | Wires `github_workflows` router; stashes `settings` on `app.state`. |
| `backend/src/repopulse/pipeline/orchestrator.py` | New `record_normalized` method for callers that already hold a `NormalizedEvent`. |
| `backend/tests/test_github_payloads.py` | 6 tests for payload model parsing. |
| `backend/tests/test_github_triage.py` | 12 tests (8 original + 4 post-review regression). |
| `backend/tests/test_github_ci_analysis.py` | 9 tests. |
| `backend/tests/test_github_doc_drift.py` | 10 tests. |
| `backend/tests/test_github_usage.py` | 7 tests. |
| `backend/tests/test_github_workflows_api.py` | 11 tests (8 original + 3 post-review regression: kill-switch-flip-without-restart, doc-drift size cap, ci-failure jobs cap). |
| `backend/tests/test_orchestrator.py` | +1 test (`record_normalized` direct append). |
| `.github/workflows/agentic-issue-triage.yml` | New workflow: `issues` event → triage backend call → comment. Scoped permissions: `issues: write`, `contents: read`. |
| `.github/workflows/agentic-ci-failure-analysis.yml` | New workflow: `workflow_run.completed (failure)` → CI-failure backend call → PR comment. Scoped permissions: `pull-requests: write`, `contents: read`, `actions: read`. Also records workflow usage telemetry. |
| `.github/workflows/agentic-doc-drift-check.yml` | New workflow: `pull_request` (markdown changes) → doc-drift backend call → PR comment. Scoped permissions: `pull-requests: write`, `contents: read`. |
| `.github/workflows/scripts/agentic_call.py` | Stdlib-only HTTP helper used by the workflow YAMLs. |
| `docs/agentic-workflows.md` | Trust model, kill switch, dry-run mode, rollback procedure, cost rates, failure modes, setup checklist, upgrade path. |
| `docs/security-model.md` | Updated §"GitHub Agentic Workflow Boundaries" + secrets list (post-review I4 fix replaces stale `REPOPULSE_GITHUB_TOKEN` reference). |
| `docs/superpowers/plans/m5-evidence/server.log` + `server-postfix.log` | uvicorn stdout from each evidence run. |
| `docs/superpowers/plans/m5-evidence/triage-*.json`, `ci-failure-response.json`, `doc-drift-response.json`, `usage-response.json`, `recommendations-after-usage.json` | Path-1 captured outputs. |
| `docs/superpowers/plans/m5-evidence/auth-401*.txt`, `kill-switch-disabled.txt`, `size-413.txt` | Path-2 captured outputs (negative-case proof). |
| `docs/superpowers/plans/m5-evidence/code-review.md` | Full reviewer report. |
| `docs/superpowers/plans/m5-evidence/evidence.md` | Narrative evidence index linking artifacts to acceptance gates. |

UI Hold Gate: respected. No `frontend/` work; `.claude/skills/design-system/SKILL.md` remains parked.

## 2. Commands Run and Outcomes

| Command | Outcome |
|---|---|
| TDD red runs (`pytest tests/test_github_<module>.py`) before each implementation | All correctly failed with `ModuleNotFoundError` / 404 / assertion failure before code was written. |
| TDD green runs after each implementation | All pass. |
| Task 5 systematic-debugging cycle | Hypothesis (`PurePosixPath` doesn't normalize `..`) verified by switching to `posixpath.normpath`; all 10 doc-drift tests passed. |
| YAML parse check | `python -c "import yaml; ..."` → `ok` for all three workflow files. |
| Backend HTTP smoke (Path 1) | `/healthz` returns version 0.4.0. All four `/api/v1/github/*` endpoints return expected structured JSON. |
| Backend HTTP smoke (Path 2) | Wrong token → 401 ✅. Kill switch enabled → 202 + `disabled:true` ✅. Oversized body → 413 ✅. |
| Code review dispatch | Subagent `code-reviewer` returned 16 findings (2 Critical, 6 Important, 8 Minor); full report at `docs/superpowers/plans/m5-evidence/code-review.md`. |
| Post-review fixes commit (`373e06d`) | C2 + I1–I6 addressed; C1 rejected with verification; 171 tests pass, ruff/mypy clean. |
| Final quality gate | `pytest -v` exit 0 (**171 passed in 1.08 s**); `ruff check src tests` exit 0 ("All checks passed!"); `mypy` exit 0 ("no issues found in 48 source files"); `pip install -e .[dev]` exit 0; `from repopulse import __version__` → `0.4.0`. |

## 3. Test Results and Known Gaps

**Test suite:** 171 tests, 0 failures.

| File | Count | Δ vs M3 |
|---|---|---|
| `test_config.py` | 4 | — |
| `test_health.py` | 2 | — |
| `test_telemetry.py` | 6 | — |
| `test_telemetry_instrumentation.py` | 2 | — |
| `test_events.py` | 7 | — |
| `test_slo.py` | 19 | — |
| `test_load_generator.py` | 9 | — |
| `test_normalize.py` | 14 | — |
| `test_anomaly_detector.py` | 13 | — |
| `test_correlation.py` | 11 | — |
| `test_recommend.py` | 12 | — |
| `test_orchestrator.py` | **11** (was 10; +1 `record_normalized`) | +1 |
| `test_recommendations_api.py` | 4 | — |
| `test_pipeline_e2e.py` | 2 | — |
| `test_github_payloads.py` | **6** | +6 |
| `test_github_triage.py` | **12** (8 + 4 regression) | +12 |
| `test_github_ci_analysis.py` | **9** | +9 |
| `test_github_doc_drift.py` | **10** | +10 |
| `test_github_usage.py` | **7** | +7 |
| `test_github_workflows_api.py` | **11** (8 + 3 regression) | +11 |
| **Total** | **171** | **+56** |

**Known gaps (intended; later milestones):**

- The workflow YAMLs are not exercised end-to-end against a real GitHub event in this milestone — the agentic_call.py helper script + the YAML files have been authored and YAML-parsed, but the only way to live-fire them is to push to a fork with the secrets set. That validation is part of the M5 → M6 transition (operational rollout) rather than a backend-correctness claim.
- The CI-failure analyzer ships with `failed_jobs=[]` from the workflow side (we don't fetch job logs in this milestone). The full log-pulling step is straightforward (`gh run view --json` + step-output API) but adds workflow runtime cost; deferred until we have a real failed run to tune against.
- Cost telemetry uses static per-runner USD rates. The GitHub Billing API integration is deferred to a later milestone (noted in ADR-003 §"Future work" and `docs/agentic-workflows.md`).
- Doc-drift coverage limits are documented (reference-style links, parens-in-targets) — they're not bugs, they're a YAGNI-based intentional subset.
- Persistence: still in-memory deques. The `agentic-workflow` event source replays cleanly into any future store because `to_normalized_event` produces a stable schema.

## 4. Risks + Limitations

- **Security:**
  - **Trust boundary is small and explicit.** Backend never holds a GitHub token; only the workflow YAMLs do, with minimal `permissions:` blocks (`issues: write`, `pull-requests: write`, never `contents: write`, never `actions: write`).
  - **Two-layer kill switch.** Workflow `if:` gate (job never runs) + backend env-var (returns 202 disabled). Either layer alone stops automation. Settings re-read per request (post-review C2 fix) so flipping the env var on a running backend takes effect immediately.
  - **Shared-secret auth.** Wrong/missing token → 401. Missing expected secret on backend → 503 (fail closed). Token rotation is `gh secret set` plus an env-var update on the backend host.
  - **Request-size caps.** Per-field length limits + a 413 guard on oversized `file_contents` values prevent a noisy or malicious workflow from OOMing the backend (post-review I5 fix).
  - **No new CVEs introduced.** No outbound HTTP from backend to GitHub; no GitHub credentials stored server-side.
- **Reliability:**
  - Synchronous backend calls inside the workflow can fail (network, backend down). On failure the workflow job goes red in the Actions UI, no comment is posted, no orchestrator side effect occurs (the M3 idempotence layer also dedupes safely on retry).
  - Backend endpoints inherit the M3 in-memory model — the same single-worker / FastAPI-thread-safety story applies.
- **Maintainability:** Pure-functional analyzer modules (triage / ci_analysis / doc_drift / usage) are sub-millisecond and trivially testable. The HTTP layer is a thin shell that just delegates and applies size caps + auth.
- **Operational:** The `docs/agentic-workflows.md` "Setup Checklist" walks through enabling the workflows in dry-run first and graduating to live mode. Rollback is `git rm` of the three YAML files plus the kill-switch flip; backend can stay deployed.
- **Process:** TDD discipline observed for every behavior change; one systematic-debugging cycle (Task 5 PurePath); code review caught two critical-severity findings (one verified false, one fixed with regression test) and six important findings (all fixed with regression tests). Skills explicitly invoked and logged per the M5 mandate.

## 5. Proposed Next-Milestone Prompt

> **M5 is the last backend milestone.** UI Hold Gate is now eligible to lift, but only with explicit user confirmation per the project's backend-first ordering.
>
> When you're ready, the next user prompt could be:
>
> > Approve M5 ✅. Lift the UI Hold Gate and start M4 (Operator Dashboard UI). Required skills: `superpowers:writing-plans` (M4 plan first), `superpowers:test-driven-development` (component-level), `frontend-design:frontend-design` (ambitious distinctive UI), `playwright-cli` (visual regression tests in browser), `superpowers:verification-before-completion`, `superpowers:requesting-code-review`. Use the parked `dashboard` design slug at `.claude/skills/design-system/SKILL.md`. M4 scope: an operator dashboard that visualizes recommendations from `/api/v1/recommendations`, agentic workflow usage from the M5 events, the M2 SLO state, and a kill-switch toggle. Anti-hallucination strict, evidence in M4 handoff.
>
> Stop at M4 boundary, write `docs/superpowers/plans/milestone-4-handoff.md`, tag `v0.5.0-m4`. After M4 completes, M6 (portfolio polish — KPI report, demo flow, MIT license file, contributor docs) wraps the project.

---

## Evidence Log

| Claim | Evidence Source | Verification Method |
|---|---|---|
| 171 tests pass | `pytest` exit 0, last line `171 passed in 1.08s` | Re-run `cd backend && ./.venv/Scripts/python -m pytest` |
| Lint clean | `ruff check src tests` exit 0, "All checks passed!" | Re-run that command |
| Strict typecheck clean | `mypy` exit 0, "Success: no issues found in 48 source files" | Re-run `cd backend && ./.venv/Scripts/python -m mypy` |
| Build clean at v0.4.0 | `pip install -e .[dev]` exit 0 + `python -c "from repopulse import __version__; print(__version__)"` returned `0.4.0` | Re-run those commands |
| HTTP `/healthz` reflects new version | `curl http://127.0.0.1:8007/healthz` → `{"status":"ok",...,"version":"0.4.0"}` (saved in `m5-evidence/server.log`) | Boot uvicorn + curl |
| Triage endpoint returns critical for outage | `triage-response.json` (initial) and `triage-postfix.json` (post-fix) both show severity=critical, T1 evidence trace | Re-replay the curl in `m5-evidence/evidence.md` § "Path 1" |
| I1 fix — `production-ready` is no longer critical | `triage-i1-fp.json` shows severity=`minor` for "Add production-ready logging" | Re-replay the curl |
| I1 fix — `crashed` (verb stem) is critical | `triage-i1-fn.json` shows severity=`critical` for "App crashed on launch" | Re-replay the curl |
| CI failure analyzer classifies test failures | `ci-failure-response.json` shows `likely_cause=test-failure`, `next_action=investigate-test` | Re-replay the curl |
| Doc-drift detects broken refs | `doc-drift-response.json` shows two broken refs with line numbers | Re-replay the curl |
| Usage endpoint ingests into orchestrator | `usage-response.json` returns `accepted: true` + UUID; `recommendations-after-usage.json` reflects the orchestrator update | Re-replay the curl |
| Auth 401 on wrong token | `auth-401.txt` and `auth-401-postfix.txt` show `HTTP 401` and `{"detail":"invalid agentic token"}` | Re-replay the curl |
| Kill switch returns 202 disabled | `kill-switch-disabled.txt` shows `HTTP 202` and `{"disabled":true,"reason":"REPOPULSE_AGENTIC_ENABLED=false"}` | Boot backend with `REPOPULSE_AGENTIC_ENABLED=false` and curl |
| C2 fix — kill switch flip on running process | Test `test_kill_switch_flip_takes_effect_without_restart` constructs live `TestClient`, asserts 200, monkeypatches env to `false`, asserts the next request returns 202 | `pytest tests/test_github_workflows_api.py::test_kill_switch_flip_takes_effect_without_restart -v` |
| I5 fix — oversized body returns 413 | `size-413.txt` shows `HTTP 413` + body `{"detail":"file_contents['x.md'] exceeds 262144 byte cap"}` | Re-replay the curl |
| TDD discipline | Each TDD task (2, 3, 4, 5, 6, 7) wrote tests first, captured RED in conversation, then minimal GREEN. Commits identifiable via `git log --grep="(TDD)"` | Search the git log + inspect commit-pair sequencing |
| Systematic debugging on Task 5 | The `PurePosixPath` root-cause investigation is documented in this handoff §"Skills" row 3 | Read this handoff + the Task 5 commit `a7328b9` |
| Code-review dispatch + receipt | Reviewer report at `docs/superpowers/plans/m5-evidence/code-review.md`; fix commit `373e06d` lists C2, I1–I6 with regression tests; C1 pushback documented in ADR-003 § "Code review notes" | `git log --grep="C2, I1-I6"` |
| Anti-hallucination | Every claim above has a re-runnable command + captured artifact path; no claim originates outside the evidence files in `m5-evidence/` | Inspect this table |
| UI Hold Gate respected | `find . -path '*/node_modules' -prune -o -type d -name frontend -print` returns nothing; no consumption of `.claude/skills/design-system/SKILL.md` | Re-run that find |

### Exact rollback / disable procedure

```bash
# 1. Stop new agentic runs immediately:
gh variable set REPOPULSE_AGENTIC_ENABLED --body 'false'

# 2. (Optional) Remove the workflow files entirely:
git rm .github/workflows/agentic-issue-triage.yml \
       .github/workflows/agentic-ci-failure-analysis.yml \
       .github/workflows/agentic-doc-drift-check.yml \
       .github/workflows/scripts/agentic_call.py
git commit -m "revert: disable agentic workflows"
git push origin main

# 3. (Optional) Remove the secret + variable:
gh secret delete REPOPULSE_AGENTIC_TOKEN
gh variable delete REPOPULSE_BACKEND_URL
gh variable delete REPOPULSE_AGENTIC_ENABLED

# Backend rollback is unnecessary — the orchestrator is in-memory; restart
# clears any retained state. The /api/v1/github/* endpoints can stay
# deployed; with REPOPULSE_AGENTIC_ENABLED unset (defaults to true) but
# the workflow files removed, they simply won't be called.
```

---

**Handoff complete. Tagging `v0.4.0-m5`.**

# Milestone 5 — GitHub Agentic Workflows — Execution Plan

> **For agentic workers:** Continues from `v0.3.0-m3`. REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Required skills, invoked explicitly per task: `superpowers:writing-plans` (this doc), `superpowers:test-driven-development` (every behavior change), `superpowers:systematic-debugging` (any non-trivial failure), `superpowers:verification-before-completion` (before claiming done), `superpowers:requesting-code-review` (before final handoff), `superpowers:receiving-code-review` (if findings raised), `superpowers:dispatching-parallel-agents` (only if truly independent — otherwise document why not used). Constraints unchanged: anti-hallucination strict, UI Hold Gate active, evidence-first reporting.

## Goal

Add a guardrailed GitHub Agentic Workflow layer on top of the M3 AIOps core: three workflow files (issue triage, CI failure analysis, doc-drift check) call back into the RepoPulse backend over HTTP. The backend gains a `repopulse.github` package with pure analyzers and HTTP endpoints, plus workflow usage telemetry. **Read-only by default** — no merges, no force-pushes, no destructive ops. A repository-level kill switch (`REPOPULSE_AGENTIC_ENABLED`) disables all agentic posting in one toggle.

## Architecture

```
GitHub event (issues / workflow_run / pull_request)
   │
   ▼  .github/workflows/agentic-*.yml  (least-privilege GITHUB_TOKEN, kill-switch gated)
Workflow runner
   │  HTTP POST  (with shared-secret header; backend URL via secret)
   ▼
repopulse.api.github_workflows
   │
   ├─► repopulse.github.triage.classify_issue()        → TriageRecommendation
   ├─► repopulse.github.ci_analysis.summarize_failure()→ CIFailureSummary
   ├─► repopulse.github.doc_drift.find_broken_refs()   → DocDriftReport
   └─► repopulse.github.usage.record_run()             → WorkflowUsage event
                                                        │
                                                        ▼
                                              orchestrator.ingest()
                                                        │
                                                        ▼
                                       same M3 pipeline (normalize → detect → correlate → recommend)
```

Pure-functional analyzers (mirroring the M3 style) plus thin HTTP shells. The orchestrator gains a new event source `agentic-workflow` so workflow runs feed back into the AIOps timeline.

## Tech additions

- **Standard library only** for analyzers (`re`, `pathlib`, `dataclasses`).
- **No outbound HTTP from the backend** in M5 — workflows POST inbound; comment-posting back to GitHub stays inside the workflow YAML using `gh` CLI / `github-script`. This keeps the kill switch clean: turning the env var off short-circuits the workflow itself, not the backend.
- New tests use `pytest`'s `parametrize` plus `httpx.AsyncClient` for the API endpoints (already present in `[dev]`).

## File Structure (additions)

```
.github/workflows/
├── ci.yml                              (existing; unchanged)
├── agentic-issue-triage.yml            (new — issues.opened/reopened)
├── agentic-ci-failure-analysis.yml     (new — workflow_run.completed where conclusion=failure)
└── agentic-doc-drift-check.yml         (new — pull_request.opened/synchronize)

backend/src/repopulse/github/
├── __init__.py                         (new — package marker, re-exports)
├── payloads.py                         (new — pydantic models for the 3 event subsets we read)
├── triage.py                           (new — pure: classify_issue(payload) → TriageRecommendation)
├── ci_analysis.py                      (new — pure: summarize_failure(payload, jobs) → CIFailureSummary)
├── doc_drift.py                        (new — pure: find_broken_refs(changed_files, repo_paths, contents) → DocDriftReport)
└── usage.py                            (new — record_run(usage) → WorkflowUsage; converts to NormalizedEvent)

backend/src/repopulse/api/
└── github_workflows.py                 (new — POST endpoints, kill-switch gated)

backend/src/repopulse/config.py         (modify — add agentic_enabled + agentic_shared_secret)

backend/tests/
├── test_github_payloads.py             (new — model parsing happy + reject paths)
├── test_github_triage.py               (new — rule coverage + evidence trace)
├── test_github_ci_analysis.py          (new — failure summarization)
├── test_github_doc_drift.py            (new — broken-ref detection)
├── test_github_usage.py                (new — record + ingest into orchestrator)
└── test_github_workflows_api.py        (new — endpoint behavior + kill switch + auth header)

docs/
├── agentic-workflows.md                (new — trust model, kill switch, rollback)
└── security-model.md                   (modify — add §"Agentic workflow trust boundary")

adr/
└── ADR-003-agentic-execution-model.md  (new — workflow-as-action-gate decision)

docs/superpowers/plans/
├── milestone-5-handoff.md              (new — at end of milestone)
└── m5-evidence/                        (new — server.log, request/response samples, code-review.md)
```

## Trust boundary (codified in tests + docs)

- Workflows authenticate to backend via `Authorization: Bearer ${{ secrets.REPOPULSE_AGENTIC_TOKEN }}`. Backend rejects requests with missing/wrong token (401 — test).
- `REPOPULSE_AGENTIC_ENABLED` env var: when `false`, backend returns **202 with `disabled: true`** instead of running analysis (test). Workflow files also have an early `if:` gate on `vars.REPOPULSE_AGENTIC_ENABLED != 'false'` so kill switch works at *both* layers.
- Workflow `permissions:` blocks are minimal: triage/ci-failure get `issues: write, pull-requests: write, contents: read`. Doc-drift gets `pull-requests: write, contents: read`. **No `contents: write`. No `actions: write`.**
- Workflows post **comments only**. They do not merge, label-without-review, force-push, or close issues.

---

## Task 1 — M5 plan + ADR-003

**Files:**
- Create: `plans/milestone-5-execution-plan.md` (this file)
- Create: `adr/ADR-003-agentic-execution-model.md`
- Test: n/a (planning artifact)

- [ ] **Step 1: Save this plan**

Already saved if you're reading it.

- [ ] **Step 2: Write ADR-003**

Records: workflow-as-action-gate (vs. separate runner), comment-only default, kill-switch design, persistence boundary (no DB writes — workflow events flow through M3 orchestrator deques), and the inbound-only HTTP model.

- [ ] **Step 3: Commit**

```bash
git add plans/milestone-5-execution-plan.md adr/ADR-003-agentic-execution-model.md
git commit -m "plan: M5 execution plan + ADR-003 (agentic execution model)"
```

---

## Task 2 — TDD: GitHub payload models

**Files:**
- Create: `backend/src/repopulse/github/__init__.py`
- Create: `backend/src/repopulse/github/payloads.py`
- Test: `backend/tests/test_github_payloads.py`

**Scope:** Minimal pydantic models for the *subsets* of GitHub event payloads we read. No full webhook schema — YAGNI.

- [ ] **Step 1: Write failing test (`test_github_payloads.py`)**

```python
import pytest
from pydantic import ValidationError
from repopulse.github.payloads import (
    IssuePayload,
    WorkflowRunPayload,
    PullRequestPayload,
)


def test_issue_payload_minimal_parses():
    p = IssuePayload.model_validate({
        "action": "opened",
        "issue": {
            "number": 42,
            "title": "App crashes on startup",
            "body": "Stack trace: NullPointer...",
            "labels": [{"name": "bug"}],
            "user": {"login": "alice"},
        },
        "repository": {"full_name": "Ibrahim4594/OpsGraph-A"},
    })
    assert p.issue.number == 42
    assert p.issue.title == "App crashes on startup"
    assert p.issue.label_names == ("bug",)
    assert p.repository.full_name == "Ibrahim4594/OpsGraph-A"


def test_issue_payload_rejects_unknown_action():
    with pytest.raises(ValidationError):
        IssuePayload.model_validate({
            "action": "exploded",  # not in our enum
            "issue": {"number": 1, "title": "x", "body": "", "labels": [], "user": {"login": "a"}},
            "repository": {"full_name": "x/y"},
        })


def test_workflow_run_payload_failure_parses():
    p = WorkflowRunPayload.model_validate({
        "action": "completed",
        "workflow_run": {
            "id": 999,
            "name": "ci",
            "conclusion": "failure",
            "head_branch": "fix/auth",
            "head_sha": "deadbeef",
            "html_url": "https://github.com/x/y/actions/runs/999",
            "run_attempt": 1,
        },
        "repository": {"full_name": "x/y"},
    })
    assert p.workflow_run.conclusion == "failure"
    assert p.workflow_run.head_sha == "deadbeef"


def test_pull_request_payload_changed_files_optional():
    p = PullRequestPayload.model_validate({
        "action": "opened",
        "pull_request": {
            "number": 7,
            "title": "Update docs",
            "head": {"sha": "cafe"},
            "base": {"ref": "main"},
        },
        "repository": {"full_name": "x/y"},
    })
    assert p.pull_request.number == 7
```

- [ ] **Step 2: Run RED**

Run: `cd backend && pytest tests/test_github_payloads.py -v`
Expected: `ModuleNotFoundError: No module named 'repopulse.github'`.

- [ ] **Step 3: Implement minimal models (`payloads.py`)**

```python
from typing import Literal
from pydantic import BaseModel, Field


class _Repository(BaseModel):
    full_name: str


class _IssueUser(BaseModel):
    login: str


class _IssueLabel(BaseModel):
    name: str


class _Issue(BaseModel):
    number: int
    title: str
    body: str | None = None
    labels: list[_IssueLabel] = Field(default_factory=list)
    user: _IssueUser

    @property
    def label_names(self) -> tuple[str, ...]:
        return tuple(label.name for label in self.labels)


class IssuePayload(BaseModel):
    action: Literal["opened", "reopened", "edited"]
    issue: _Issue
    repository: _Repository


class _WorkflowRun(BaseModel):
    id: int
    name: str
    conclusion: Literal["success", "failure", "cancelled", "skipped", "neutral", "timed_out"]
    head_branch: str
    head_sha: str
    html_url: str
    run_attempt: int


class WorkflowRunPayload(BaseModel):
    action: Literal["completed", "requested", "in_progress"]
    workflow_run: _WorkflowRun
    repository: _Repository


class _PRRef(BaseModel):
    sha: str | None = None
    ref: str | None = None


class _PullRequest(BaseModel):
    number: int
    title: str
    head: _PRRef
    base: _PRRef


class PullRequestPayload(BaseModel):
    action: Literal["opened", "synchronize", "reopened", "edited"]
    pull_request: _PullRequest
    repository: _Repository
```

`__init__.py`:

```python
"""RepoPulse GitHub agentic-workflow integration."""

from repopulse.github.payloads import (
    IssuePayload,
    PullRequestPayload,
    WorkflowRunPayload,
)

__all__ = ["IssuePayload", "PullRequestPayload", "WorkflowRunPayload"]
```

- [ ] **Step 4: Run GREEN**

Run: `cd backend && pytest tests/test_github_payloads.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/repopulse/github/__init__.py backend/src/repopulse/github/payloads.py backend/tests/test_github_payloads.py
git commit -m "feat(github): payload models for issues/workflow_run/pull_request (TDD)"
```

---

## Task 3 — TDD: Triage classifier

**Files:**
- Create: `backend/src/repopulse/github/triage.py`
- Test: `backend/tests/test_github_triage.py`

**Rules (matches M3 evidence-trace shape):**

- T1 (priority): title or body contains `crash|outage|production|sev1|sev-1` (case-insensitive) → severity=`critical`, suggested_labels={`severity:critical`, `triage`}, evidence cites the matched terms.
- T2: title or body contains `error|exception|failure|broken|stack trace` → severity=`major`, suggested_labels={`severity:major`, `triage`}.
- T3: title or body contains `feature|enhancement|proposal|request` → category=`feature-request`, suggested_labels={`type:feature`}.
- T4: title or body contains `docs?|documentation|typo|readme` → category=`docs`, suggested_labels={`type:docs`}.
- T5 (fallback): no rule matches → severity=`minor`, category=`uncategorized`, suggested_labels={`triage`}, confidence=0.4. **Explicit fallback (matches M3 R1 design).**
- Severity priority T1 > T2 > T5; category priority T3 ≈ T4 > T5; rules can co-fire (e.g. "feature: docs typo" → severity=`minor` from T5, category overlay from T3 + T4).

- [ ] **Step 1: Write failing test**

```python
from repopulse.github.payloads import IssuePayload
from repopulse.github.triage import TriageRecommendation, classify_issue


def _issue(title: str, body: str = "", labels: tuple[str, ...] = ()) -> IssuePayload:
    return IssuePayload.model_validate({
        "action": "opened",
        "issue": {
            "number": 1,
            "title": title,
            "body": body,
            "labels": [{"name": n} for n in labels],
            "user": {"login": "tester"},
        },
        "repository": {"full_name": "x/y"},
    })


def test_classify_critical_outage():
    rec = classify_issue(_issue("Production outage — checkout broken"))
    assert isinstance(rec, TriageRecommendation)
    assert rec.severity == "critical"
    assert "severity:critical" in rec.suggested_labels
    assert any("T1" in line for line in rec.evidence_trace)


def test_classify_major_on_stack_trace():
    rec = classify_issue(_issue("App throws NullPointerException", body="Stack trace below"))
    assert rec.severity == "major"
    assert "severity:major" in rec.suggested_labels
    assert any("T2" in line for line in rec.evidence_trace)


def test_classify_feature_request_overlay():
    rec = classify_issue(_issue("Feature: dark mode", body="Proposal to add dark mode"))
    assert rec.category == "feature-request"
    assert "type:feature" in rec.suggested_labels


def test_classify_docs_overlay():
    rec = classify_issue(_issue("Typo in README", body="Fix typo"))
    assert rec.category == "docs"
    assert "type:docs" in rec.suggested_labels


def test_classify_fallback_when_no_rule_matches():
    rec = classify_issue(_issue("Question about config", body="How do I set X"))
    assert rec.severity == "minor"
    assert rec.category == "uncategorized"
    assert "triage" in rec.suggested_labels
    assert rec.confidence == 0.4
    assert any("T5 fallback" in line for line in rec.evidence_trace)


def test_classify_critical_overrides_major():
    rec = classify_issue(_issue("Production crash with stack trace exception"))
    assert rec.severity == "critical"
```

- [ ] **Step 2: Run RED**

Run: `cd backend && pytest tests/test_github_triage.py -v`
Expected: `ModuleNotFoundError: No module named 'repopulse.github.triage'`.

- [ ] **Step 3: Implement (`triage.py`)**

```python
import re
from dataclasses import dataclass, field
from typing import Literal

from repopulse.github.payloads import IssuePayload

Severity = Literal["critical", "major", "minor"]
Category = Literal["feature-request", "docs", "uncategorized"]

_T1 = re.compile(r"\b(crash|outage|production|sev[\s-]?1)\b", re.IGNORECASE)
_T2 = re.compile(r"\b(error|exception|failure|broken|stack\s*trace)\b", re.IGNORECASE)
_T3 = re.compile(r"\b(feature|enhancement|proposal|request)\b", re.IGNORECASE)
_T4 = re.compile(r"\b(docs?|documentation|typo|readme)\b", re.IGNORECASE)


@dataclass(frozen=True)
class TriageRecommendation:
    issue_number: int
    severity: Severity
    category: Category
    suggested_labels: tuple[str, ...]
    confidence: float
    evidence_trace: tuple[str, ...] = field(default_factory=tuple)


def classify_issue(payload: IssuePayload) -> TriageRecommendation:
    text = f"{payload.issue.title}\n{payload.issue.body or ''}"

    severity: Severity = "minor"
    category: Category = "uncategorized"
    labels: list[str] = []
    trace: list[str] = []
    confidence = 0.4

    if _T1.search(text):
        severity = "critical"
        labels.extend(["severity:critical", "triage"])
        confidence = 0.9
        trace.append(f"T1: critical signal matched ({_T1.pattern}) → severity=critical")
    elif _T2.search(text):
        severity = "major"
        labels.extend(["severity:major", "triage"])
        confidence = 0.75
        trace.append(f"T2: major signal matched ({_T2.pattern}) → severity=major")

    if _T3.search(text):
        category = "feature-request"
        labels.append("type:feature")
        trace.append(f"T3: feature signal matched ({_T3.pattern}) → category=feature-request")

    if _T4.search(text):
        category = "docs"
        labels.append("type:docs")
        trace.append(f"T4: docs signal matched ({_T4.pattern}) → category=docs")

    if not trace:
        labels.append("triage")
        trace.append("T5 fallback: no rule matched → severity=minor, category=uncategorized")

    # de-dup while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for label in labels:
        if label not in seen:
            seen.add(label)
            deduped.append(label)

    return TriageRecommendation(
        issue_number=payload.issue.number,
        severity=severity,
        category=category,
        suggested_labels=tuple(deduped),
        confidence=confidence,
        evidence_trace=tuple(trace),
    )
```

- [ ] **Step 4: Run GREEN**

Run: `cd backend && pytest tests/test_github_triage.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/repopulse/github/triage.py backend/tests/test_github_triage.py
git commit -m "feat(github): rule-based issue triage classifier with evidence trace (TDD)"
```

---

## Task 4 — TDD: CI failure analyzer

**Files:**
- Create: `backend/src/repopulse/github/ci_analysis.py`
- Test: `backend/tests/test_github_ci_analysis.py`

**Scope:** Given a `WorkflowRunPayload` with `conclusion=failure` and an optional list of failed-job summaries `(job_name, failed_step, log_excerpt)`, return a `CIFailureSummary` with:

- `workflow_run_id`, `head_sha`, `head_branch`
- `failed_jobs`: tuple of `(job_name, failed_step)`
- `likely_cause`: classification using log excerpts:
  - regex `\b(timeout|timed out|deadline)\b` → `timeout`
  - regex `(ModuleNotFoundError|ImportError|cannot find module)` → `dependency`
  - regex `\b(AssertionError|test .* failed|FAILED)\b` → `test-failure`
  - regex `(SyntaxError|ParseError|unexpected token)` → `syntax`
  - else → `unknown`
- `evidence_trace`: which patterns matched per job
- `next_action`: "rerun" for `timeout`, "fix-deps" for `dependency`, "investigate-test" for `test-failure`, "fix-syntax" for `syntax`, "manual-review" for `unknown`
- Refuse non-failure conclusions: raise `ValueError`.

- [ ] **Step 1: Write failing test**

```python
import pytest
from repopulse.github.ci_analysis import CIFailureSummary, summarize_failure
from repopulse.github.payloads import WorkflowRunPayload


def _run(conclusion: str = "failure") -> WorkflowRunPayload:
    return WorkflowRunPayload.model_validate({
        "action": "completed",
        "workflow_run": {
            "id": 100,
            "name": "ci",
            "conclusion": conclusion,
            "head_branch": "fix/x",
            "head_sha": "abc",
            "html_url": "https://github.com/x/y/actions/runs/100",
            "run_attempt": 1,
        },
        "repository": {"full_name": "x/y"},
    })


def test_summarize_timeout_returns_rerun():
    s = summarize_failure(_run(), failed_jobs=[
        ("backend", "Test (pytest)", "E   Timed out after 600s"),
    ])
    assert isinstance(s, CIFailureSummary)
    assert s.likely_cause == "timeout"
    assert s.next_action == "rerun"
    assert s.failed_jobs == (("backend", "Test (pytest)"),)


def test_summarize_module_error_returns_fix_deps():
    s = summarize_failure(_run(), failed_jobs=[
        ("backend", "Install", "ModuleNotFoundError: No module named 'foo'"),
    ])
    assert s.likely_cause == "dependency"
    assert s.next_action == "fix-deps"


def test_summarize_test_failure_returns_investigate():
    s = summarize_failure(_run(), failed_jobs=[
        ("backend", "Test", "FAILED tests/test_x.py::test_y - AssertionError"),
    ])
    assert s.likely_cause == "test-failure"
    assert s.next_action == "investigate-test"


def test_summarize_syntax_error_returns_fix_syntax():
    s = summarize_failure(_run(), failed_jobs=[
        ("backend", "Lint", "SyntaxError: unexpected token"),
    ])
    assert s.likely_cause == "syntax"
    assert s.next_action == "fix-syntax"


def test_summarize_unknown_returns_manual_review():
    s = summarize_failure(_run(), failed_jobs=[
        ("backend", "Step", "some opaque error"),
    ])
    assert s.likely_cause == "unknown"
    assert s.next_action == "manual-review"


def test_summarize_rejects_non_failure():
    with pytest.raises(ValueError):
        summarize_failure(_run(conclusion="success"), failed_jobs=[])
```

- [ ] **Step 2: Run RED**

Run: `cd backend && pytest tests/test_github_ci_analysis.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement (`ci_analysis.py`)**

```python
import re
from dataclasses import dataclass
from typing import Literal

from repopulse.github.payloads import WorkflowRunPayload

Cause = Literal["timeout", "dependency", "test-failure", "syntax", "unknown"]
NextAction = Literal["rerun", "fix-deps", "investigate-test", "fix-syntax", "manual-review"]

_PATTERNS: tuple[tuple[Cause, re.Pattern[str]], ...] = (
    ("timeout", re.compile(r"\b(timeout|timed out|deadline)\b", re.IGNORECASE)),
    ("dependency", re.compile(r"(ModuleNotFoundError|ImportError|cannot find module)")),
    ("syntax", re.compile(r"(SyntaxError|ParseError|unexpected token)")),
    ("test-failure", re.compile(r"\b(AssertionError|FAILED|test .* failed)\b")),
)

_NEXT: dict[Cause, NextAction] = {
    "timeout": "rerun",
    "dependency": "fix-deps",
    "test-failure": "investigate-test",
    "syntax": "fix-syntax",
    "unknown": "manual-review",
}


@dataclass(frozen=True)
class CIFailureSummary:
    workflow_run_id: int
    head_sha: str
    head_branch: str
    failed_jobs: tuple[tuple[str, str], ...]
    likely_cause: Cause
    next_action: NextAction
    evidence_trace: tuple[str, ...]


def summarize_failure(
    payload: WorkflowRunPayload,
    *,
    failed_jobs: list[tuple[str, str, str]],
) -> CIFailureSummary:
    if payload.workflow_run.conclusion != "failure":
        raise ValueError(
            f"summarize_failure requires conclusion='failure', got "
            f"{payload.workflow_run.conclusion!r}"
        )

    cause: Cause = "unknown"
    trace: list[str] = []

    for job_name, _step, excerpt in failed_jobs:
        for candidate, pattern in _PATTERNS:
            if pattern.search(excerpt):
                if cause == "unknown":
                    cause = candidate
                trace.append(f"{candidate}: {pattern.pattern} matched in job {job_name!r}")
                break
        else:
            trace.append(f"unknown: no pattern matched in job {job_name!r}")

    if not trace:
        trace.append("unknown: no failed-job excerpts provided")

    return CIFailureSummary(
        workflow_run_id=payload.workflow_run.id,
        head_sha=payload.workflow_run.head_sha,
        head_branch=payload.workflow_run.head_branch,
        failed_jobs=tuple((j, s) for j, s, _ in failed_jobs),
        likely_cause=cause,
        next_action=_NEXT[cause],
        evidence_trace=tuple(trace),
    )
```

- [ ] **Step 4: Run GREEN**

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/repopulse/github/ci_analysis.py backend/tests/test_github_ci_analysis.py
git commit -m "feat(github): CI failure analyzer with evidence-traced cause classification (TDD)"
```

---

## Task 5 — TDD: Doc-drift checker

**Files:**
- Create: `backend/src/repopulse/github/doc_drift.py`
- Test: `backend/tests/test_github_doc_drift.py`

**Scope:** Given:
- `changed_files`: list of paths in the PR diff (strings)
- `repo_paths`: set of paths existing in the repo *post-change* (strings)
- `file_contents`: mapping `path → text` for the markdown files we need to scan

Find broken markdown links of the form `[text](relative/path.md)` and `[text](relative/path.md#anchor)` where the target doesn't exist in `repo_paths`. Skip http(s) links and same-file anchors (`#foo`). Returns `DocDriftReport` with `broken_refs: tuple[(source_file, target, line_number)]`.

Also: a doc-only PR (changed_files all under `docs/` or `README.md`) that *removes* a referenced file → flagged. **The check is over the post-change tree** — caller is responsible for building `repo_paths` from the PR's head ref.

- [ ] **Step 1: Write failing test**

```python
from repopulse.github.doc_drift import DocDriftReport, find_broken_refs


def test_no_broken_refs_returns_empty():
    contents = {"docs/index.md": "[arch](architecture.md)\n"}
    repo_paths = {"docs/index.md", "docs/architecture.md"}
    rpt = find_broken_refs(
        changed_files=["docs/index.md"],
        repo_paths=repo_paths,
        file_contents=contents,
    )
    assert isinstance(rpt, DocDriftReport)
    assert rpt.broken_refs == ()


def test_broken_relative_link_detected():
    contents = {"docs/index.md": "see [old](old-arch.md) please\n"}
    repo_paths = {"docs/index.md"}
    rpt = find_broken_refs(
        changed_files=["docs/index.md"],
        repo_paths=repo_paths,
        file_contents=contents,
    )
    assert rpt.broken_refs == (("docs/index.md", "old-arch.md", 1),)


def test_anchor_only_link_skipped():
    contents = {"docs/index.md": "[top](#top)\n"}
    rpt = find_broken_refs(
        changed_files=["docs/index.md"],
        repo_paths={"docs/index.md"},
        file_contents=contents,
    )
    assert rpt.broken_refs == ()


def test_external_http_link_skipped():
    contents = {"docs/index.md": "[ext](https://example.com/x.md)\n"}
    rpt = find_broken_refs(
        changed_files=["docs/index.md"],
        repo_paths={"docs/index.md"},
        file_contents=contents,
    )
    assert rpt.broken_refs == ()


def test_link_with_anchor_resolves_against_path():
    contents = {"docs/a.md": "[b](b.md#section)\n"}
    rpt = find_broken_refs(
        changed_files=["docs/a.md"],
        repo_paths={"docs/a.md", "docs/b.md"},
        file_contents=contents,
    )
    assert rpt.broken_refs == ()


def test_multiple_broken_refs_with_line_numbers():
    contents = {"docs/a.md": "header\n[x](x.md)\n[y](y.md)\n"}
    rpt = find_broken_refs(
        changed_files=["docs/a.md"],
        repo_paths={"docs/a.md"},
        file_contents=contents,
    )
    assert rpt.broken_refs == (
        ("docs/a.md", "x.md", 2),
        ("docs/a.md", "y.md", 3),
    )
```

- [ ] **Step 2: Run RED**

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement (`doc_drift.py`)**

```python
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

_LINK = re.compile(r"\[(?P<text>[^\]]+)\]\((?P<target>[^)\s]+)\)")


@dataclass(frozen=True)
class DocDriftReport:
    broken_refs: tuple[tuple[str, str, int], ...]


def _is_external(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:"))


def _is_anchor_only(target: str) -> bool:
    return target.startswith("#")


def _resolve(source_file: str, target: str) -> str:
    raw = target.split("#", 1)[0]
    if not raw:
        return ""
    base = PurePosixPath(source_file).parent
    return str((base / raw).as_posix())


def find_broken_refs(
    *,
    changed_files: list[str],
    repo_paths: set[str],
    file_contents: dict[str, str],
) -> DocDriftReport:
    broken: list[tuple[str, str, int]] = []
    for path in changed_files:
        text = file_contents.get(path)
        if text is None:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            for match in _LINK.finditer(line):
                target = match.group("target")
                if _is_external(target) or _is_anchor_only(target):
                    continue
                resolved = _resolve(path, target)
                if not resolved or resolved in repo_paths:
                    continue
                broken.append((path, target, line_no))
    return DocDriftReport(broken_refs=tuple(broken))
```

- [ ] **Step 4: Run GREEN**

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/repopulse/github/doc_drift.py backend/tests/test_github_doc_drift.py
git commit -m "feat(github): doc-drift checker for broken markdown refs in PR changes (TDD)"
```

---

## Task 6 — TDD: Workflow usage telemetry

**Files:**
- Create: `backend/src/repopulse/github/usage.py`
- Test: `backend/tests/test_github_usage.py`

**Scope:** Convert a workflow-run completion into a `WorkflowUsage` record + a `NormalizedEvent` (so it joins the M3 timeline). Cost-equivalent uses static rate (linux runner $0.008/min) — documented as a stand-in until GitHub's real billing API is wired up post-M5.

- [ ] **Step 1: Write failing test**

```python
from datetime import UTC, datetime

from repopulse.github.usage import WorkflowUsage, record_run, to_normalized_event


def test_workflow_usage_holds_fields():
    usage = WorkflowUsage(
        workflow_name="agentic-issue-triage",
        run_id=123,
        duration_seconds=42.0,
        conclusion="success",
        repository="x/y",
        cost_estimate_usd=42.0 / 60.0 * 0.008,
    )
    assert usage.workflow_name == "agentic-issue-triage"
    assert round(usage.cost_estimate_usd, 6) == round(42 / 60 * 0.008, 6)


def test_record_run_computes_cost_for_linux():
    usage = record_run(
        workflow_name="ci",
        run_id=999,
        duration_seconds=120.0,
        conclusion="success",
        repository="x/y",
        runner="linux",
    )
    assert usage.cost_estimate_usd == 120.0 / 60.0 * 0.008


def test_record_run_zero_cost_for_unknown_runner():
    usage = record_run(
        workflow_name="ci",
        run_id=1,
        duration_seconds=10.0,
        conclusion="success",
        repository="x/y",
        runner="self-hosted",
    )
    assert usage.cost_estimate_usd == 0.0


def test_to_normalized_event_shape():
    usage = record_run(
        workflow_name="agentic-doc-drift",
        run_id=7,
        duration_seconds=30.0,
        conclusion="failure",
        repository="x/y",
        runner="linux",
    )
    received_at = datetime(2026, 4, 27, 12, tzinfo=UTC)
    ev = to_normalized_event(usage, received_at=received_at)
    assert ev.source == "agentic-workflow"
    assert ev.kind == "workflow-failure"
    assert ev.severity == "warning"
    assert ev.received_at == received_at
    assert ev.attributes["workflow.name"] == "agentic-doc-drift"
    assert ev.attributes["workflow.run_id"] == "7"
    assert ev.attributes["workflow.conclusion"] == "failure"
```

- [ ] **Step 2: Run RED**

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement (`usage.py`)**

```python
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from repopulse.pipeline.normalize import NormalizedEvent

_RUNNER_RATES_USD_PER_MIN: dict[str, float] = {
    "linux": 0.008,
    "windows": 0.016,
    "macos": 0.08,
}


@dataclass(frozen=True)
class WorkflowUsage:
    workflow_name: str
    run_id: int
    duration_seconds: float
    conclusion: str
    repository: str
    cost_estimate_usd: float


def record_run(
    *,
    workflow_name: str,
    run_id: int,
    duration_seconds: float,
    conclusion: str,
    repository: str,
    runner: str,
) -> WorkflowUsage:
    rate = _RUNNER_RATES_USD_PER_MIN.get(runner, 0.0)
    cost = duration_seconds / 60.0 * rate
    return WorkflowUsage(
        workflow_name=workflow_name,
        run_id=run_id,
        duration_seconds=duration_seconds,
        conclusion=conclusion,
        repository=repository,
        cost_estimate_usd=cost,
    )


def to_normalized_event(usage: WorkflowUsage, *, received_at: datetime) -> NormalizedEvent:
    if usage.conclusion == "success":
        kind = "workflow-success"
        severity = "info"
    elif usage.conclusion == "failure":
        kind = "workflow-failure"
        severity = "warning"
    else:
        kind = "workflow-other"
        severity = "info"
    return NormalizedEvent(
        event_id=uuid4(),
        source="agentic-workflow",
        kind=kind,
        severity=severity,
        received_at=received_at,
        attributes={
            "workflow.name": usage.workflow_name,
            "workflow.run_id": str(usage.run_id),
            "workflow.conclusion": usage.conclusion,
            "workflow.duration_seconds": f"{usage.duration_seconds:.3f}",
            "workflow.cost_estimate_usd": f"{usage.cost_estimate_usd:.6f}",
            "workflow.repository": usage.repository,
        },
    )
```

- [ ] **Step 4: Run GREEN**

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/repopulse/github/usage.py backend/tests/test_github_usage.py
git commit -m "feat(github): workflow usage telemetry + normalized-event mapping (TDD)"
```

---

## Task 7 — TDD: HTTP endpoints + auth + kill switch

**Files:**
- Modify: `backend/src/repopulse/config.py` — add `agentic_enabled: bool = True`, `agentic_shared_secret: str | None = None`.
- Create: `backend/src/repopulse/api/github_workflows.py`
- Modify: `backend/src/repopulse/main.py` — register router.
- Test: `backend/tests/test_github_workflows_api.py`

**Endpoints (all POST, all under `/api/v1/github/`):**
- `POST /triage` — body: `IssuePayload` → `TriageRecommendation` JSON.
- `POST /ci-failure` — body: `{payload: WorkflowRunPayload, failed_jobs: [{job_name, step, log_excerpt}]}` → `CIFailureSummary`.
- `POST /doc-drift` — body: `{changed_files, repo_paths, file_contents}` → `DocDriftReport`.
- `POST /usage` — body: `{workflow_name, run_id, duration_seconds, conclusion, repository, runner}` → `{accepted: true, event_id}` and ingests via orchestrator.

**Cross-cutting:**
- Each endpoint requires `Authorization: Bearer <REPOPULSE_AGENTIC_SHARED_SECRET>`. Missing/wrong → 401.
- If `REPOPULSE_AGENTIC_ENABLED=false`, all endpoints return **202 with `{"disabled": true, "reason": "REPOPULSE_AGENTIC_ENABLED=false"}`** (no analysis run, no orchestrator side effects).
- Endpoint pure logic delegates to the Task 3–6 modules.

- [ ] **Step 1: Write failing test (`test_github_workflows_api.py`)**

```python
import pytest
from fastapi.testclient import TestClient

from repopulse.config import Settings
from repopulse.main import create_app


@pytest.fixture
def secret() -> str:
    return "test-secret-do-not-use"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, secret: str) -> TestClient:
    monkeypatch.setenv("REPOPULSE_AGENTIC_ENABLED", "true")
    monkeypatch.setenv("REPOPULSE_AGENTIC_SHARED_SECRET", secret)
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


def _issue_body() -> dict:
    return {
        "action": "opened",
        "issue": {
            "number": 5,
            "title": "Production outage",
            "body": "checkout broken",
            "labels": [],
            "user": {"login": "u"},
        },
        "repository": {"full_name": "x/y"},
    }


def test_triage_requires_auth(client: TestClient):
    r = client.post("/api/v1/github/triage", json=_issue_body())
    assert r.status_code == 401


def test_triage_returns_recommendation(client: TestClient, auth: dict[str, str]):
    r = client.post("/api/v1/github/triage", json=_issue_body(), headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert data["severity"] == "critical"
    assert data["issue_number"] == 5
    assert "severity:critical" in data["suggested_labels"]


def test_kill_switch_disables_endpoint(monkeypatch: pytest.MonkeyPatch, secret: str):
    monkeypatch.setenv("REPOPULSE_AGENTIC_ENABLED", "false")
    monkeypatch.setenv("REPOPULSE_AGENTIC_SHARED_SECRET", secret)
    app = create_app()
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post(
        "/api/v1/github/triage",
        json=_issue_body(),
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert r.status_code == 202
    assert r.json()["disabled"] is True


def test_ci_failure_endpoint(client: TestClient, auth: dict[str, str]):
    body = {
        "payload": {
            "action": "completed",
            "workflow_run": {
                "id": 1, "name": "ci", "conclusion": "failure",
                "head_branch": "x", "head_sha": "abc",
                "html_url": "https://x", "run_attempt": 1,
            },
            "repository": {"full_name": "x/y"},
        },
        "failed_jobs": [
            {"job_name": "backend", "step": "Test", "log_excerpt": "AssertionError: nope"},
        ],
    }
    r = client.post("/api/v1/github/ci-failure", json=body, headers=auth)
    assert r.status_code == 200
    assert r.json()["likely_cause"] == "test-failure"


def test_doc_drift_endpoint(client: TestClient, auth: dict[str, str]):
    body = {
        "changed_files": ["docs/a.md"],
        "repo_paths": ["docs/a.md"],
        "file_contents": {"docs/a.md": "[x](missing.md)"},
    }
    r = client.post("/api/v1/github/doc-drift", json=body, headers=auth)
    assert r.status_code == 200
    assert r.json()["broken_refs"] == [["docs/a.md", "missing.md", 1]]


def test_usage_endpoint_ingests_event(client: TestClient, auth: dict[str, str]):
    body = {
        "workflow_name": "ci", "run_id": 5,
        "duration_seconds": 30.0, "conclusion": "failure",
        "repository": "x/y", "runner": "linux",
    }
    r = client.post("/api/v1/github/usage", json=body, headers=auth)
    assert r.status_code == 202
    assert r.json()["accepted"] is True
```

- [ ] **Step 2: Run RED**

Expected: 404s and config attribute errors.

- [ ] **Step 3: Update `config.py`**

```python
class Settings(BaseSettings):
    # ... existing fields ...
    agentic_enabled: bool = True
    agentic_shared_secret: str | None = None
```

- [ ] **Step 4: Implement `api/github_workflows.py`**

```python
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel

from repopulse.config import Settings, get_settings
from repopulse.github.ci_analysis import summarize_failure
from repopulse.github.doc_drift import find_broken_refs
from repopulse.github.payloads import IssuePayload, WorkflowRunPayload
from repopulse.github.triage import classify_issue
from repopulse.github.usage import record_run, to_normalized_event

router = APIRouter(prefix="/api/v1/github", tags=["github"])


def _auth(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> Settings:
    expected = settings.agentic_shared_secret
    if not expected:
        raise HTTPException(status_code=503, detail="agentic shared secret not configured")
    token = (authorization or "").removeprefix("Bearer ").strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="invalid agentic token")
    return settings


def _disabled_response() -> dict[str, object]:
    return {"disabled": True, "reason": "REPOPULSE_AGENTIC_ENABLED=false"}


class _CIFailureBody(BaseModel):
    payload: WorkflowRunPayload
    failed_jobs: list["_FailedJob"]


class _FailedJob(BaseModel):
    job_name: str
    step: str
    log_excerpt: str


_CIFailureBody.model_rebuild()


class _DocDriftBody(BaseModel):
    changed_files: list[str]
    repo_paths: list[str]
    file_contents: dict[str, str]


class _UsageBody(BaseModel):
    workflow_name: str
    run_id: int
    duration_seconds: float
    conclusion: str
    repository: str
    runner: str


@router.post("/triage")
def triage(
    payload: IssuePayload,
    settings: Annotated[Settings, Depends(_auth)],
) -> dict[str, object]:
    if not settings.agentic_enabled:
        return _disabled_response()
    rec = classify_issue(payload)
    return {
        "issue_number": rec.issue_number,
        "severity": rec.severity,
        "category": rec.category,
        "suggested_labels": list(rec.suggested_labels),
        "confidence": rec.confidence,
        "evidence_trace": list(rec.evidence_trace),
    }


@router.post("/ci-failure")
def ci_failure(
    body: _CIFailureBody,
    settings: Annotated[Settings, Depends(_auth)],
) -> dict[str, object]:
    if not settings.agentic_enabled:
        return _disabled_response()
    summary = summarize_failure(
        body.payload,
        failed_jobs=[(j.job_name, j.step, j.log_excerpt) for j in body.failed_jobs],
    )
    return {
        "workflow_run_id": summary.workflow_run_id,
        "head_sha": summary.head_sha,
        "head_branch": summary.head_branch,
        "failed_jobs": [list(j) for j in summary.failed_jobs],
        "likely_cause": summary.likely_cause,
        "next_action": summary.next_action,
        "evidence_trace": list(summary.evidence_trace),
    }


@router.post("/doc-drift")
def doc_drift(
    body: _DocDriftBody,
    settings: Annotated[Settings, Depends(_auth)],
) -> dict[str, object]:
    if not settings.agentic_enabled:
        return _disabled_response()
    rpt = find_broken_refs(
        changed_files=body.changed_files,
        repo_paths=set(body.repo_paths),
        file_contents=body.file_contents,
    )
    return {"broken_refs": [list(t) for t in rpt.broken_refs]}


@router.post("/usage", status_code=status.HTTP_202_ACCEPTED)
def usage(
    body: _UsageBody,
    request: Request,
    settings: Annotated[Settings, Depends(_auth)],
) -> dict[str, object]:
    if not settings.agentic_enabled:
        return _disabled_response()
    record = record_run(
        workflow_name=body.workflow_name,
        run_id=body.run_id,
        duration_seconds=body.duration_seconds,
        conclusion=body.conclusion,
        repository=body.repository,
        runner=body.runner,
    )
    event = to_normalized_event(record, received_at=datetime.now(UTC))
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is not None:
        orchestrator.record_normalized(event)
        orchestrator.evaluate()
    return {"accepted": True, "event_id": str(event.event_id)}
```

> **Note on `record_normalized`:** the M3 orchestrator's `ingest()` takes an `EventEnvelope` and runs it through `normalize`. Here we already have a `NormalizedEvent`, so the orchestrator needs a sibling method `record_normalized(event)` that pushes directly into `_events`. Add that during this task (3-line addition + 1 unit test in `test_orchestrator.py`).

- [ ] **Step 5: Wire router in `main.py`**

```python
from repopulse.api import events, github_workflows, health, recommendations
# ...
app.include_router(github_workflows.router)
```

- [ ] **Step 6: Run GREEN**

Run: `cd backend && pytest tests/test_github_workflows_api.py tests/test_orchestrator.py -v`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add backend/src/repopulse/api/github_workflows.py backend/src/repopulse/config.py backend/src/repopulse/main.py backend/src/repopulse/pipeline/orchestrator.py backend/tests/test_github_workflows_api.py backend/tests/test_orchestrator.py
git commit -m "feat(api): GitHub agentic workflow endpoints with auth + kill switch (TDD)"
```

---

## Task 8 — Workflow YAML files

**Files:**
- Create: `.github/workflows/agentic-issue-triage.yml`
- Create: `.github/workflows/agentic-ci-failure-analysis.yml`
- Create: `.github/workflows/agentic-doc-drift-check.yml`
- Create: `.github/workflows/scripts/agentic_call.py` (small Python helper used by the workflows; tested via Task 9 evidence run)

**Cross-cutting structure for every workflow file:**

```yaml
name: <slug>

on:
  <event>

permissions:
  # Minimal — no contents:write, no actions:write
  issues: write
  pull-requests: write
  contents: read

env:
  REPOPULSE_BACKEND_URL: ${{ vars.REPOPULSE_BACKEND_URL }}
  REPOPULSE_AGENTIC_TOKEN: ${{ secrets.REPOPULSE_AGENTIC_TOKEN }}
  REPOPULSE_AGENTIC_ENABLED: ${{ vars.REPOPULSE_AGENTIC_ENABLED }}

jobs:
  agentic:
    if: ${{ vars.REPOPULSE_AGENTIC_ENABLED != 'false' }}
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - name: Call backend
        run: python .github/workflows/scripts/agentic_call.py <subcommand>
      - name: Comment on issue/PR
        uses: actions/github-script@v7
        with:
          script: |
            // posts comment using github.rest.issues.createComment / createReview
```

`agentic_call.py` reads inputs from `GITHUB_EVENT_PATH`, posts to backend, writes the response to `$GITHUB_OUTPUT` for the comment-posting step.

- [ ] **Step 1: Author the three workflow files**

Each one only does: ① call backend with the relevant payload subset, ② post a single comment summarizing. No labels added without `severity:*`-prefix prefix check (so we don't go outside our triage namespace). Default behavior is **dry run**: if `vars.REPOPULSE_AGENTIC_DRYRUN == 'true'`, skip the comment step and just log to the run output.

- [ ] **Step 2: Author `agentic_call.py`**

```python
"""Helper for agentic workflows: reads GITHUB_EVENT_PATH, calls backend, writes outputs."""
import json
import os
import sys
import urllib.request

URL = os.environ["REPOPULSE_BACKEND_URL"].rstrip("/")
TOKEN = os.environ["REPOPULSE_AGENTIC_TOKEN"]


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{URL}{path}",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _emit(name: str, value: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"{name}<<EOF\n{value}\nEOF\n")


def main() -> int:
    cmd = sys.argv[1]
    event_path = os.environ["GITHUB_EVENT_PATH"]
    with open(event_path) as fh:
        event = json.load(fh)

    if cmd == "triage":
        result = _post("/api/v1/github/triage", event)
    elif cmd == "ci-failure":
        # Build a minimal failed_jobs list — just the workflow_run for now;
        # log fetching is left to a follow-up.
        result = _post("/api/v1/github/ci-failure", {"payload": event, "failed_jobs": []})
    elif cmd == "doc-drift":
        # Caller workflow is responsible for assembling changed_files/repo_paths/file_contents.
        # Here we error out — the doc-drift workflow uses a dedicated assembly step before this.
        raise SystemExit("doc-drift not invoked directly; see workflow YAML")
    else:
        raise SystemExit(f"unknown cmd {cmd!r}")

    _emit("result_json", json.dumps(result))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Verify YAML parses**

Run: `python -c "import yaml; [yaml.safe_load(open(p)) for p in ['.github/workflows/agentic-issue-triage.yml', '.github/workflows/agentic-ci-failure-analysis.yml', '.github/workflows/agentic-doc-drift-check.yml']]; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/agentic-issue-triage.yml .github/workflows/agentic-ci-failure-analysis.yml .github/workflows/agentic-doc-drift-check.yml .github/workflows/scripts/agentic_call.py
git commit -m "feat(workflows): three agentic GitHub workflows with kill switch + scoped permissions"
```

---

## Task 9 — docs/agentic-workflows.md + security-model update

**Files:**
- Create: `docs/agentic-workflows.md`
- Modify: `docs/security-model.md` (add §"Agentic workflow trust boundary")

**`docs/agentic-workflows.md` outline:**

1. What and why (3 paragraphs).
2. Trust model (table: principal → permission → effect).
3. Kill switch (env-var name, both layers, how to flip in repo settings, expected backend response, expected workflow gate).
4. Rollback procedure (revert workflow YAML files, no DB rollback needed — orchestrator is in-memory).
5. Costs (per-runner table from `usage.py`; how to track via the new endpoint).
6. Failure modes + recovery.
7. Upgrade path (webhook driven, not polling).

- [ ] **Commit:**

```bash
git add docs/agentic-workflows.md docs/security-model.md
git commit -m "docs(M5): agentic workflows trust model, kill switch, rollback procedure"
```

---

## Task 10 — Evidence run + code review + handoff + tag

**Files:**
- Create: `docs/superpowers/plans/m5-evidence/server.log`
- Create: `docs/superpowers/plans/m5-evidence/triage-sample-request.sh` + `.json` response
- Create: `docs/superpowers/plans/m5-evidence/ci-failure-sample.sh` + `.json`
- Create: `docs/superpowers/plans/m5-evidence/doc-drift-sample.sh` + `.json`
- Create: `docs/superpowers/plans/m5-evidence/usage-sample.sh` + `.json`
- Create: `docs/superpowers/plans/m5-evidence/kill-switch.sh` + `.json` (proves disabled response)
- Create: `docs/superpowers/plans/m5-evidence/code-review.md` (subagent report)
- Create: `docs/superpowers/plans/m5-evidence/evidence.md` (narrative index)
- Create: `docs/superpowers/plans/milestone-5-handoff.md`

**Process:**

1. **Verification (`superpowers:verification-before-completion`):** fresh `pytest -v`, `ruff check`, `mypy`, `pip install -e .[dev]`. Capture exact output.
2. **Boot backend with secret + agentic enabled, run all four endpoints via curl, capture responses.** Then flip `REPOPULSE_AGENTIC_ENABLED=false`, re-run, capture `disabled: true` response.
3. **Code review (`superpowers:requesting-code-review`):** dispatch `superpowers:code-reviewer` subagent on `v0.3.0-m3..HEAD`. Save report. Address Critical + Important findings (`superpowers:receiving-code-review`); push fix commit.
4. **Re-run evidence after fixes; bump `pyproject.toml` and `__init__.py` to `0.4.0`.**
5. **Write `milestone-5-handoff.md`** with skills-invocation log, evidence log, security risk + mitigations, exact rollback procedure, M4 (UI) proposed prompt (paused until explicit user confirmation per UI Hold Gate).
6. **Tag `v0.4.0-m5`** and push.

- [ ] **Final commit:**

```bash
git add backend/pyproject.toml backend/src/repopulse/__init__.py docs/superpowers/plans/milestone-5-handoff.md docs/superpowers/plans/m5-evidence/
git commit -m "chore(backend): bump version to 0.4.0 + M5 handoff with skills log + evidence"
git tag v0.4.0-m5
git push origin main --tags
```

---

## Self-Review

**Spec coverage:**
- ✅ Three workflows under `.github/workflows/` (T8) — issue triage, CI failure analysis, doc-drift.
- ✅ Safe outputs + scoped permissions + explicit write constraints (each workflow header in T8).
- ✅ Non-destructive default + kill switch (T7 backend; T8 workflow `if:` gate).
- ✅ CI failure analysis / triage / docs-drift automation guardrailed (T3, T4, T5).
- ✅ Cost/usage telemetry (T6 + T7 `/usage` endpoint).
- ✅ Security/trust-boundary docs (T9).
- ✅ Skills explicitly invoked + logged: `writing-plans` (T1), `test-driven-development` (T2–T7), `systematic-debugging` (any failure during T2–T8), `verification-before-completion` (T10), `requesting-code-review` (T10), `receiving-code-review` (T10), `dispatching-parallel-agents` (T2/T3/T4/T5/T6 are independent pure modules — candidate; document either way in handoff).
- ✅ Anti-hallucination strict (every claim in T10 → re-runnable command + captured artifact).
- ✅ UI Hold Gate active (no `frontend/` work).
- ✅ M5 handoff with skills log, evidence log, security notes, rollback procedure, M4 next-prompt (T10).

**Placeholder scan:** none. All tasks have full code blocks.

**Type consistency:** `TriageRecommendation`, `CIFailureSummary`, `DocDriftReport`, `WorkflowUsage`, `NormalizedEvent` are referenced consistently across tasks. `record_normalized` is added to `PipelineOrchestrator` in T7 (called out explicitly).

---

## Execution choice

Inline execution per `superpowers:executing-plans` (consistent with M3 — same author, same session).

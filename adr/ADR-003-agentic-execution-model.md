# ADR-003: Agentic GitHub Workflow Execution Model

- **Status:** Accepted
- **Date:** 2026-04-27
- **Deciders:** Project owner (Ibrahim)
- **Supersedes:** —
- **Superseded by:** —

## Context

Milestone 5 introduces GitHub Agentic Workflows on top of the M3 AIOps core. These workflows must:

1. React to repository events (`issues`, `workflow_run`, `pull_request`).
2. Call into the RepoPulse backend for analysis (triage, CI failure summarization, doc-drift detection).
3. Surface results back to the repository (comments).
4. Stay safe — no destructive operations, no merging, no force-pushing — and be cleanly **disable-able** via a single toggle.
5. Emit cost/usage telemetry so we can show stakeholders what the automation is spending.

There are several plausible execution shapes. We picked one and rejected the others. Rationale below.

## Decision

### 1. Workflow-as-action-gate (the chosen model)

GitHub Actions workflow files (`.github/workflows/agentic-*.yml`) are the *only* component that has write access to the repository. They:

- POST a subset of the GitHub event payload to the RepoPulse backend over HTTP.
- Receive a structured analysis result (`TriageRecommendation`, `CIFailureSummary`, `DocDriftReport`).
- Post a single comment summarizing that result, using `actions/github-script` with the workflow's scoped `GITHUB_TOKEN`.

The backend never holds a GitHub token. The backend never calls GitHub. **All write actions live in workflow YAML, where the permissions block is explicit and reviewable.** This is the action-gate: the workflow is the only thing that can write, and the workflow can only do what its `permissions:` declaration allows.

### 2. Inbound-only HTTP between workflow and backend

The workflow → backend direction is the only network direction we use in M5. No webhooks (yet), no polling. Implications:

- Backend's attack surface is unchanged structurally (still an HTTP POST endpoint), only widened by the new `/api/v1/github/*` routes.
- No long-running listener; existing FastAPI app handles the new endpoints synchronously.
- Authentication is a shared secret (`Authorization: Bearer <REPOPULSE_AGENTIC_SHARED_SECRET>`) stored in repo Secrets and read from `vars.REPOPULSE_AGENTIC_TOKEN` inside the workflow. Token rotation is a one-line `gh secret set` away.

### 3. Two-layer kill switch via `REPOPULSE_AGENTIC_ENABLED`

When the operator wants automation off:

- **Workflow layer:** every `agentic-*.yml` file has `if: ${{ vars.REPOPULSE_AGENTIC_ENABLED != 'false' }}` on the `agentic` job. If the variable is set to `false` at the repo level, the job never runs — no API calls, no comments.
- **Backend layer:** if a stale workflow somehow reaches the backend, `Settings.agentic_enabled=False` causes every `/api/v1/github/*` endpoint to return `202 {"disabled": true, ...}` instead of executing the analyzer or pushing into the orchestrator.

Both layers are needed because workflow files are eventually-consistent across forks/clones; the backend layer is the authoritative "stop now" control. Setting `REPOPULSE_AGENTIC_ENABLED=false` once on the backend disables the entire surface within milliseconds.

### 4. No persistence beyond M3 deques

Workflow events flow through the orchestrator's in-memory deques the same as any other event. We do not introduce a database in M5. Rationale:

- M3 explicitly defers persistence; M5 should not silently revoke that deferral.
- Workflow metadata is reproducible from GitHub itself (`gh run view <id>`); we don't need our own canonical store.
- The `WorkflowUsage` event is a `NormalizedEvent` with `source="agentic-workflow"` and a stable attribute schema, so when persistence does land later, replaying from GitHub's API into the same orchestrator produces the same state.

### 5. Comments as the only write effect

The three workflows can:

- Add a comment to the issue (triage workflow).
- Add a comment to the PR's run page or commit (CI failure workflow).
- Post a review comment on the PR (doc-drift workflow).

They cannot:

- Add labels (deferred — needs a follow-up ADR if we ever want it; would also need a label-namespace whitelist to prevent the workflow from "stealing" non-triage labels).
- Close issues/PRs.
- Merge anything.
- Push commits, including no force-pushes.
- Delete branches.
- Edit existing comments (post-only, never edit/delete).

This is enforced by the `permissions:` block in each workflow file. `contents: write` and `actions: write` are absent.

### 6. Dry-run mode

Every agentic workflow honors `vars.REPOPULSE_AGENTIC_DRYRUN`. When set to `true`, the workflow runs the analysis and writes the result to the run log (visible in the Actions UI), but **skips the comment-posting step**. This is the recommended mode for first install and during stakeholder review.

## Alternatives considered

### Separate runner / agent service

A standalone process subscribes to GitHub webhooks, holds a `GITHUB_APP` token, and writes to the repo directly. Rejected because:

- Adds an always-on dependency (a process to run, monitor, and pay for).
- Token surface is larger than a per-workflow `GITHUB_TOKEN` and easier to misuse.
- Permissions are coarser (GitHub Apps don't have the per-job least-privilege model that workflow `permissions:` blocks have).
- Kill switch becomes "stop the process" — riskier under partial failure (process up but blocked) than the two-layer flag.

### Backend-initiated outbound calls to GitHub

Backend holds a token and calls the GitHub REST API. Rejected because:

- Doubles the secret surface (backend now holds a GitHub credential, not just a workflow shared secret).
- Inverts the trust direction — backend pushes into GitHub instead of GitHub pulling from backend — which complicates the kill switch (you'd have to guarantee backend stops, instead of just disabling the inbound endpoint).
- Forces us to write GitHub API client code inside the backend now, when we only need it for write effects we explicitly chose to defer to the workflow YAML.

### "Just label, don't comment"

Tried in early sketch. Rejected because labels mutate the repo's tag namespace silently — easy to add, hard to spot, and harder to roll back. Comments are visible, dated, attributable to the workflow, and trivially deleteable.

## Consequences

### Positive

- Trust boundary is **explicit and small**: workflow YAML + four backend endpoints. Reviewable in one sitting.
- Kill switch is **one repo variable away**, with belt-and-braces enforcement at both layers.
- Cost telemetry comes from the workflow runs themselves, which is the only authoritative source.
- Backend does not gain a GitHub token, which keeps the M3 attack surface intact.
- Rollback is `git revert` of the three workflow files — backend code can stay deployed (it just stops being called).

### Negative

- Workflow YAML duplicates a small amount of orchestration logic across the three files (kill-switch gate, env wiring, backend call). Acceptable for three workflows; if we add a fourth, factor into a reusable workflow or composite action (M5.5 / M6 candidate).
- Comments-only output means we can't "fix" anything, only suggest. Operators have to act manually. That's the explicit M5 design — automation that fixes things lives in a future milestone with its own ADR.
- Synchronous backend calls inside the workflow can fail (network, backend down). The workflow then fails the job, which the operator can see in the Actions UI. We do not retry from the workflow side because retried POSTs against the M3 idempotence layer (C2 dedup) are safe but add cost.

### Neutral / future work

- Webhook-driven mode (skip the workflow runner, deliver events straight to the backend over HMAC-signed webhooks) is a clear next step but requires either an external dispatcher or a public backend. Deferred.
- Cost telemetry uses static per-runner rates (`linux=$0.008/min`). Real billing comes from the GitHub Billing API, which we'll wire when we have a real billing context to compare against.
- Persistence: when the orchestrator gets a real store, the `agentic-workflow` event source replays cleanly because it's already a `NormalizedEvent` with a stable attribute schema.

## Code review notes (post-tag fixes applied 2026-04-27)

The M5 code review (`docs/superpowers/plans/m5-evidence/code-review.md`) flagged 2 Critical and 6 Important findings. Status:

- **C1 (body validation runs before auth):** rejected after verification. Live-server curl with a malformed body and no auth header returned `401 invalid agentic token`, not `422` — FastAPI resolves the auth dependency before body validation in this stack. The reviewer's claim could not be reproduced.
- **C2 (settings frozen at startup):** confirmed and fixed. `_get_settings` now constructs a fresh `Settings()` per request so flipping `REPOPULSE_AGENTIC_ENABLED` or rotating `REPOPULSE_AGENTIC_SHARED_SECRET` takes effect immediately. Regression test: `test_kill_switch_flip_takes_effect_without_restart`.
- **I1 (triage `production` over-triggers, `crashed` under-triggers):** fixed. `production` only matches when paired with an incident-shaped word (`production-down`, `production-broken`, etc.), and the `crash` pattern now accepts verb stems (`crashed`/`crashing`/`crashes`). Regression tests added.
- **I2 (CI analyzer first-job-wins):** documented in the module docstring with rationale.
- **I3 (doc-drift regex coverage):** documented as known limitations in the module docstring (reference-style links and parens-in-targets are out of scope; our markdown uses inline links).
- **I4 (`security-model.md` listed `REPOPULSE_GITHUB_TOKEN`):** fixed; that env var was never introduced and is replaced by `REPOPULSE_AGENTIC_SHARED_SECRET` + `REPOPULSE_AGENTIC_ENABLED`, consistent with this ADR.
- **I5 (no request-size limits):** fixed. Per-field length caps on the API body models, plus a 413 guard on `file_contents` values. Regression tests: `test_doc_drift_rejects_oversized_file_content`, `test_ci_failure_rejects_too_many_jobs`.
- **I6 (T3/T4 precedence undocumented):** documented in `triage.py` module docstring; T4 wins the `category` field on collision but both labels are emitted. Regression test: `test_classify_t3_t4_collision_t4_wins_category`.

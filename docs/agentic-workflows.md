# Agentic GitHub Workflows (M5)

This document describes the three GitHub Agentic Workflows that ship with RepoPulse, the trust model they operate under, the kill switch, the rollback procedure, and how to monitor cost/usage. The architecture decisions behind this design are recorded in [ADR-003](../adr/ADR-003-agentic-execution-model.md).

## What and Why

RepoPulse's M3 AIOps core (normalize → detect → correlate → recommend) produces structured suggestions from synthetic events. M5 extends that core with three real GitHub event sources, each implemented as a workflow file under `.github/workflows/`:

| Workflow | Trigger | Backend route | Output |
|---|---|---|---|
| `agentic-issue-triage.yml` | `issues.opened` / `reopened` / `edited` | `POST /api/v1/github/triage` | Comment on the issue: severity, category, suggested labels, evidence trace |
| `agentic-ci-failure-analysis.yml` | `workflow_run.completed` (when `conclusion=failure`) | `POST /api/v1/github/ci-failure` | Comment on the associated PR: likely cause, next action, evidence trace |
| `agentic-doc-drift-check.yml` | `pull_request.opened` / `synchronize` / `reopened` (when markdown files change) | `POST /api/v1/github/doc-drift` | Comment on the PR: list of broken markdown references with file:line |

All three are **read-only by default**. None of them merge, push, force-push, label without review, close issues, or edit existing comments.

## Trust Model

The trust boundary follows ADR-003: workflows are the only component with write access to the repository, and the backend never holds a GitHub token.

| Principal | Permission | Effect |
|---|---|---|
| Workflow `agentic-issue-triage` | `issues: write` + `contents: read` | Can post one comment per issue. Cannot close, label, lock. |
| Workflow `agentic-ci-failure-analysis` | `pull-requests: write` + `contents: read` + `actions: read` | Can post one comment on the PR. Cannot re-run the failed job. |
| Workflow `agentic-doc-drift-check` | `pull-requests: write` + `contents: read` | Can post one comment on the PR. Cannot edit files. |
| Backend `/api/v1/github/*` endpoints | None on GitHub | Pure analyzers; only side effect is appending to in-memory orchestrator deques. |

Authentication between workflow and backend is a shared bearer token:
- Workflow side: `secrets.REPOPULSE_AGENTIC_TOKEN`.
- Backend side: env var `REPOPULSE_AGENTIC_SHARED_SECRET`.

Mismatched token → 401. Missing backend secret → 503 (never accept any token when none is expected — fail closed).

## Kill Switch — `REPOPULSE_AGENTIC_ENABLED`

Two independent layers, either one stops the automation completely.

### Layer 1: Workflow gate

Each `agentic-*.yml` has `if: ${{ vars.REPOPULSE_AGENTIC_ENABLED != 'false' }}` on the analysis job. When the repo-level variable is set to `'false'`, the job never runs — no API calls, no comments, no usage telemetry, no compute cost.

To set the variable:

```bash
gh variable set REPOPULSE_AGENTIC_ENABLED --body 'false'
```

To re-enable:

```bash
gh variable delete REPOPULSE_AGENTIC_ENABLED   # default behavior is "enabled"
# or
gh variable set REPOPULSE_AGENTIC_ENABLED --body 'true'
```

### Layer 2: Backend gate

If a stale or replayed workflow somehow reaches the backend, the env var `REPOPULSE_AGENTIC_ENABLED=false` causes every `/api/v1/github/*` endpoint to return:

```json
{
  "disabled": true,
  "reason": "REPOPULSE_AGENTIC_ENABLED=false"
}
```

with HTTP status `202 Accepted`. No analyzer runs. No orchestrator state changes. The 202 (rather than 200) signals "your request was received but intentionally not processed."

### Dry-Run Mode — `REPOPULSE_AGENTIC_DRYRUN`

Set `vars.REPOPULSE_AGENTIC_DRYRUN='true'` to run the analysis but skip the final comment-posting step. The analysis result still appears in the Actions log, so you can review what the workflow would have said without touching the issue or PR. Recommended mode for the first install or for stakeholder review.

## Rollback Procedure

If you need to remove the agentic workflows entirely:

1. Set the kill switch first to stop new runs:
   ```bash
   gh variable set REPOPULSE_AGENTIC_ENABLED --body 'false'
   ```
2. Revert the workflow files:
   ```bash
   git rm .github/workflows/agentic-issue-triage.yml \
          .github/workflows/agentic-ci-failure-analysis.yml \
          .github/workflows/agentic-doc-drift-check.yml \
          .github/workflows/scripts/agentic_call.py
   git commit -m "revert: disable agentic workflows"
   git push origin main
   ```
3. (Optional) Remove the secret and variable:
   ```bash
   gh secret delete REPOPULSE_AGENTIC_TOKEN
   gh variable delete REPOPULSE_BACKEND_URL
   gh variable delete REPOPULSE_AGENTIC_ENABLED
   ```

**No backend rollback is required.** The orchestrator is in-memory; restarting the backend (or just leaving it running with `REPOPULSE_AGENTIC_ENABLED=false`) clears any retained state. Database persistence is deferred — see [ADR-002](../adr/ADR-002-aiops-core-algorithms.md) and [ADR-003](../adr/ADR-003-agentic-execution-model.md).

## Cost & Usage

GitHub-hosted runner costs (current as of 2026-04-27):

| Runner | USD / minute |
|---|---|
| `linux` | 0.008 |
| `windows` | 0.016 |
| `macos` | 0.080 |
| `self-hosted` / unknown | 0.000 (rate not tracked) |

The backend's `/api/v1/github/usage` endpoint accepts each completed workflow run, computes cost using the table above, and ingests a `NormalizedEvent` with `source="agentic-workflow"` and attributes:

- `workflow.name`
- `workflow.run_id`
- `workflow.conclusion`
- `workflow.duration_seconds`
- `workflow.cost_estimate_usd`
- `workflow.repository`

You can query the latest snapshot via `GET /api/v1/recommendations` (these events feed the M3 timeline) or, in a future milestone, via a dedicated `/api/v1/usage/summary` endpoint.

The static rate table is a stand-in until the GitHub Billing API is wired up. See [ADR-003 §6 Future Work](../adr/ADR-003-agentic-execution-model.md#neutral--future-work).

## Failure Modes & Recovery

| Failure | Symptom | Recovery |
|---|---|---|
| Backend unreachable | Workflow step fails with `URLError`; no comment posted | Workflow shows red ✗ in Actions UI. Re-run after backend is up, or set kill switch. |
| Wrong shared secret | Backend returns 401 | Workflow step fails with HTTP 401. Update `REPOPULSE_AGENTIC_TOKEN` secret to match backend's `REPOPULSE_AGENTIC_SHARED_SECRET`. |
| Backend mis-configured (no secret) | Backend returns 503 | Set `REPOPULSE_AGENTIC_SHARED_SECRET` on the backend host. |
| Stale workflow file deployed | Job calls a removed endpoint and 404s | Set kill switch; remove or update the workflow file. |
| Comment posting hits rate limit | `actions/github-script` step fails | Workflow step fails red. The analysis ran (visible in step output), only the comment is missing. Re-run the job. |

## Setup Checklist

To enable the workflows in this repo:

1. Set the backend URL as a repo variable:
   ```bash
   gh variable set REPOPULSE_BACKEND_URL --body 'https://your-backend.example.com'
   ```
2. Generate a strong shared secret (32+ bytes) and set it on both sides:
   ```bash
   SECRET=$(openssl rand -hex 32)
   gh secret set REPOPULSE_AGENTIC_TOKEN --body "$SECRET"
   # On the backend host:
   export REPOPULSE_AGENTIC_SHARED_SECRET="$SECRET"
   export REPOPULSE_AGENTIC_ENABLED=true
   ```
3. Start in dry-run mode for the first 24-48 hours:
   ```bash
   gh variable set REPOPULSE_AGENTIC_DRYRUN --body 'true'
   ```
4. Watch a few runs in the Actions UI. Check the analysis output looks reasonable.
5. Disable dry-run when ready:
   ```bash
   gh variable delete REPOPULSE_AGENTIC_DRYRUN
   ```

## Upgrade Path (post-M5)

The current model is workflow-runner driven (poll-style: GitHub fires an event → workflow → backend). A future milestone will add an optional webhook path (GitHub fires a signed HTTPS POST → backend), which removes the workflow-runner cold-start cost and the per-event compute charge but requires a public backend URL and HMAC signature verification. Both modes will coexist; the workflow path stays as the safe default with the same kill switch.

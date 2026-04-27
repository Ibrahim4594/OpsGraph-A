# Security Model

## Threat Model

**Trusted:** code in this repository, the developer's local machine, GitHub Actions runners running CI on `main`-branch workflows, the FastAPI service's own internal modules.

**Not trusted:** any payload arriving over the network — GitHub webhooks, OpenTelemetry exporters, operator browsers (eventual UI milestone), pull-request CI runs from forks. Inputs are validated against schemas at the ingest boundary; malformed events are rejected with structured errors and logged for triage.

The most sensitive operations (action gate → GitHub write paths) are explicitly excluded from any "automatic" path: a human approval state is required before any destructive recommendation reaches the GitHub adapter.

## Action Gate Principles

1. **Read-only by default.** Every recommendation type starts in a read-only category. Promotion to a write category requires an explicit policy entry.
2. **Human approval for destructive ops.** Categories that mutate repository state (close issue, merge PR, push, delete branch) cannot execute without an `approved` state recorded by an operator.
3. **Audit trail.** Every recommendation, its evidence trace, the operator who approved (or rejected) it, and the resulting action outcome are persisted before the action runs.
4. **Reversible-first preference.** Where a reversible action exists (comment instead of close, label instead of merge), it is preferred and offered alongside the destructive variant.

## Secret Handling

All runtime configuration that is sensitive flows through environment variables prefixed `REPOPULSE_` (handled by the `Settings` model in `backend/src/repopulse/config.py`). Concretely:

- `REPOPULSE_AGENTIC_SHARED_SECRET` — bearer token used by agentic workflows to authenticate to the backend (M5). The backend never holds a GitHub token; write effects live in the workflow YAML, gated by the workflow's own `GITHUB_TOKEN`. See [ADR-003](../adr/ADR-003-agentic-execution-model.md) for the rationale.
- `REPOPULSE_AGENTIC_ENABLED` — kill switch (M5). When set to `false`, all agentic endpoints return `202 {"disabled": true}`.
- `REPOPULSE_OTEL_EXPORTER_OTLP_ENDPOINT` — collector endpoint (M2).
- `REPOPULSE_REDIS_URL` — event bus connection string (M2/M3).
- `REPOPULSE_DATABASE_URL` — timeseries store connection (M3).

`.env` is gitignored at the repo root; CI provides values via repository/environment secrets. The `Settings` model rejects unknown env keys (`extra="ignore"` keeps things permissive at runtime, but documented keys are the only ones referenced).

## GitHub Agentic Workflow Boundaries

The M5 GitHub workflows that consume recommendations operate under these constraints (full details in [agentic-workflows.md](agentic-workflows.md) and [ADR-003](../adr/ADR-003-agentic-execution-model.md)):

- **Scoped tokens.** Each workflow has its own `permissions:` block declaring exactly the access it needs — `issues: write` + `contents: read` for triage, `pull-requests: write` + `contents: read` + `actions: read` for CI failure analysis, `pull-requests: write` + `contents: read` for doc drift. **No `contents: write`. No `actions: write`. No admin scopes.** Backend never holds a GitHub token.
- **Comment-only output.** Workflows post a single comment per event. They cannot label, close, merge, push, force-push, delete branches, or edit existing comments.
- **No force-push, no merges.** The token's permission set makes these structurally impossible — not just blocked at the action layer.
- **Two-layer kill switch.** The repository variable `REPOPULSE_AGENTIC_ENABLED=false` short-circuits both (a) the workflow `if:` gate (job never runs) and (b) the backend endpoint (returns `202 {"disabled": true}` with no analysis or orchestrator side effects). Either layer alone is sufficient to stop automation.
- **Shared-secret authentication.** Workflow → backend uses `Authorization: Bearer ${{ secrets.REPOPULSE_AGENTIC_TOKEN }}`. Wrong/missing token → 401. Missing expected secret in backend env → 503 (fail closed; never accept any token when no expected token is configured).
- **Cost/usage telemetry.** Every workflow run emits a `repopulse-workflow-usage` event ingested by the orchestrator with `source="agentic-workflow"`. Cost is computed from the static GitHub-hosted runner rate table.
- **Dry-run mode.** `vars.REPOPULSE_AGENTIC_DRYRUN=true` runs analysis but skips the comment-posting step, so the result is visible in the Actions log without touching the issue/PR.

## Out of Scope (M1)

User authentication for the eventual operator dashboard, network policy / VPC design, encryption-at-rest configuration, and disaster recovery procedures are out of scope until their respective milestones (M3 for storage, the UI milestone for auth). This document will be updated as those milestones land.

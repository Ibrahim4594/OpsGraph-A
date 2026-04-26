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

- `REPOPULSE_GITHUB_TOKEN` — scoped GitHub token for the agentic workflows path (M5). Never committed; loaded from `.env` (gitignored) or the deployment environment.
- `REPOPULSE_OTEL_EXPORTER_OTLP_ENDPOINT` — collector endpoint (M2).
- `REPOPULSE_REDIS_URL` — event bus connection string (M2/M3).
- `REPOPULSE_DATABASE_URL` — timeseries store connection (M3).

`.env` is gitignored at the repo root; CI provides values via repository/environment secrets. The `Settings` model rejects unknown env keys (`extra="ignore"` keeps things permissive at runtime, but documented keys are the only ones referenced).

## GitHub Agentic Workflow Boundaries

When M5 lands, the GitHub workflows that consume recommendations operate under these constraints:

- **Scoped tokens.** A least-privilege `GITHUB_TOKEN` (or fine-grained PAT) for each workflow — `issues:write` for triage, `contents:read` for doc drift, etc. No `admin:repo` tokens.
- **No force-push.** `--force` and `--force-with-lease` are blocked at the action layer.
- **No merge to `main` without review.** Branch protection on `main` requires PR review; agentic workflows can comment, label, or open PRs but cannot merge.
- **Disable mechanism.** A repository variable `REPOPULSE_AGENTIC_ENABLED=false` short-circuits all workflow runs. Documented in the M5 README.
- **Cost/usage telemetry.** Each workflow run emits a usage event so cost/scale impact is observable.

## Out of Scope (M1)

User authentication for the eventual operator dashboard, network policy / VPC design, encryption-at-rest configuration, and disaster recovery procedures are out of scope until their respective milestones (M3 for storage, the UI milestone for auth). This document will be updated as those milestones land.

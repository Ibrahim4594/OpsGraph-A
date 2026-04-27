# Runbook — `escalate`

## When this fires

Rule R3: at least two anomalies in the incident, OR at least one critical event/anomaly. Confidence 0.85, risk `medium`. Multiple correlated signals mean the system is actively unhappy.

## Default state

`pending`. Approve / Reject buttons visible.

## What you do

1. Read the **evidence trace** in the card; R3's line tells you `anomalies=N, any_critical=True/False`.
2. Open `Incidents` (sidebar) and find the incident referenced by `incident_id`. The timeline card shows the time bounds and source breakdown.
3. Pull the actual events from the OpenTelemetry collector (or the backend's recent logs at `docs/superpowers/plans/m{2,3,5}-evidence/server.log` if reproducing locally).
4. Decide:
   - **Approve** if the signal is real and on-call should be paged. M4 doesn't page automatically — this is a record that the operator made the call. Follow your team's existing paging path (PagerDuty, Slack `#oncall`, etc.).
   - **Reject** if the noise is duplicated or a known testing artifact. Always add a `reason` so the rule can be tuned later.

## What this never does automatically

- No paging.
- No status-page updates.
- No service mutations.

## Tuning hint

If R3 fires repeatedly for the same source pair (e.g. `github` + `otel-logs`) on benign events, the correlation window (`window_seconds`, default 300) may be too wide. Discuss adjustments via an ADR before changing the default.

## Related

- [ADR-002 — AIOps core algorithms](../../adr/ADR-002-aiops-core-algorithms.md).
- [ADR-004 — Approval gate model](../../adr/ADR-004-approval-gate-model.md).

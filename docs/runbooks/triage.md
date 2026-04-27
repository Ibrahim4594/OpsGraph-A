# Runbook — `triage`

## When this fires

Rule R2: exactly one anomaly, no critical events. Confidence 0.70, risk `low`. The signal is real but small — not alarming on its own.

## Default state

`pending`. The dashboard's recommendations inbox shows Approve / Reject buttons.

## What you do

1. Click into the recommendation card and read the **evidence trace**. The R2 line names the anomaly's source (`series_name`).
2. Cross-check the source's recent traffic in the OTel Collector logs (`infra/docker-compose.yml` runs the collector in dev).
3. Decide:
   - **Approve** if the anomaly is genuine and someone should look at the underlying service. Approval is *advisory* in M4 — no automation runs on approve. The Action history simply records that you accepted the suggestion.
   - **Reject** if the anomaly is a known false positive or an artifact of a deploy. Add a one-line `reason` so the next operator doesn't repeat the investigation.

## What this never does automatically

- No GitHub issues created.
- No PRs labeled or merged.
- No service restarts or rollbacks.

## Related

- [ADR-002 — AIOps core algorithms](../../adr/ADR-002-aiops-core-algorithms.md) for the R2 threshold rationale.
- [ADR-004 — Approval gate model](../../adr/ADR-004-approval-gate-model.md) for the state-machine guarantees.

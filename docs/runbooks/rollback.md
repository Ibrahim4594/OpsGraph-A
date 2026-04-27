# Runbook — `rollback`

## When this fires

Rule R4: multi-source incident (≥ 2 distinct sources) AND at least one critical anomaly or event. Confidence 0.90, risk `high`. This is the strongest signal the engine produces.

## Default state

`pending`. Approve / Reject buttons visible.

## What you do — read the evidence first

1. The recommendation card lists every rule that fired (R3 will also be in the trace because R3 is a strict subset of R4's preconditions).
2. The **incident card** under `Incidents` shows the source set — typically `github` + `otel-metrics` + `otel-logs`. A real rollback case usually correlates a deploy event with a metric spike and an error-log spike within the 5-minute window.
3. Compare the timing of the most recent successful build and the head of `main` (`git log -1`).

## Decision criteria

- **Approve** only if you have separately confirmed (a) the recent change is the likely cause and (b) reverting it is safer than rolling forward. Approval is a **record of intent**, not an automation trigger.
- **Reject** if the multi-source correlation is coincidental (e.g. a planned cron, a load-test). Always include a `reason` so the rule's risk threshold can be reviewed.

## What still must happen by hand

- The actual `git revert` / deploy-rollback is **not** triggered by approving the recommendation.
- The dashboard exists to help you make the call faster, not to replace the deploy pipeline.

## Why this isn't automated

ADR-003 § "Action Gate Principles" — destructive operations require a human approval state recorded by an operator. M4 records the state; an automated rollback runner is a future-milestone decision with its own ADR + risk analysis.

## Related

- [ADR-002 — AIOps core algorithms](../../adr/ADR-002-aiops-core-algorithms.md) for the R4 priority story.
- [ADR-003 — Agentic execution model](../../adr/ADR-003-agentic-execution-model.md) for why automation doesn't pull this trigger.
- [ADR-004 — Approval gate model](../../adr/ADR-004-approval-gate-model.md) for the state machine.

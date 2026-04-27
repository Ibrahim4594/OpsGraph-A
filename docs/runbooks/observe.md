# Runbook — `observe`

## When this fires

The recommendation engine emits `action_category="observe"` (rule R1, the explicit fallback) whenever an incident exists but none of R2–R4 match — typically:

- A single benign event with no anomalies.
- An anomaly so faint that no rule asks for action.

## Default state

`observed` — auto-transitioned at emission time. No operator action is required. The entry appears in `Action history` with `actor=system, kind=observe` so the audit trail stays complete.

## What you do

Nothing. This runbook exists so the inbox can link consistently for every action category.

## When to escalate manually

- If you see a sustained stream of observe entries from the **same source** during a known degradation, that's signal that an R2/R3 rule probably *should* fire. File an issue against the rule thresholds in [`adr/ADR-002-aiops-core-algorithms.md`](../../adr/ADR-002-aiops-core-algorithms.md).
- If the observe stream stops abruptly (no events arriving), check the OpenTelemetry collector and the FastAPI `/healthz` endpoint.

## Related

- [ADR-002 — AIOps core algorithms](../../adr/ADR-002-aiops-core-algorithms.md) for the rule-priority story.
- [ADR-004 — Approval gate model](../../adr/ADR-004-approval-gate-model.md) for why observe auto-transitions.

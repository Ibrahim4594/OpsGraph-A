# RepoPulse AIOps

Production-grade AIOps reference project: observability, AI-assisted operations with guardrails, and measurable reliability outcomes. Backend-first development; operator UI lands at the end.

> Active milestone plans live in [`plans/`](plans/). High-level roadmap: [`plans/aiops-detailed-implementation-plan.md`](plans/aiops-detailed-implementation-plan.md). Current execution plan: [`plans/milestone-1-execution-plan.md`](plans/milestone-1-execution-plan.md).

## Repository Layout

- `backend/` — FastAPI service + AIOps core (Python 3.14)
- `infra/` — local Docker Compose + OTel collector (M2+)
- `docs/` — architecture, SLO spec, security model, runbooks
- `adr/` — Architecture Decision Records
- `.github/workflows/` — CI

The operator dashboard (`frontend/`) is deferred to a final UI milestone after the AIOps core is shipped.

## Status

| Milestone | Scope | Status |
|---|---|---|
| M1 | Backend foundation | In progress |
| M2 | Observability + SLO baseline | Planned |
| M3 | AIOps core (detection / correlation / recommendations) | Planned |
| M5 | GitHub agentic workflows | Planned |
| M4 | Operator UI (dashboard) | Planned (last) |
| M6 | Portfolio polish | Planned (last) |

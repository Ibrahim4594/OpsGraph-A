# Roadmap

Source of truth for milestone scope is [`../plans/aiops-detailed-implementation-plan.md`](../plans/aiops-detailed-implementation-plan.md). Active execution plan: [`../plans/milestone-1-execution-plan.md`](../plans/milestone-1-execution-plan.md).

**Execution order is backend-first** — UI is deferred to the end so the AIOps core ships before any dashboard work begins. This differs from the parent plan's nominal milestone numbering.

| Order | Milestone | Goal | Acceptance Criteria | Status |
|---|---|---|---|---|
| 1 | **M1 — Foundation (Backend)** | Professional skeleton + delivery pipeline for the backend. | preflight-checklist; backend starts locally; CI green; base docs land. | In progress |
| 2 | **M2 — Observability + SLO Baseline** | Trustworthy telemetry before adding AI logic. | RED metrics emitted; SLO burn-rate computable; runbook stub. | Planned |
| 3 | **M3 — AIOps Core** | Detection / correlation / recommendations with explainable outputs. | Every recommendation includes evidence; correlation groups events; unit tests cover decision functions. | Planned |
| 4 | **M5 — GitHub Agentic Workflows** | Safe GitHub-native automation with guardrails. | Write ops constrained; non-destructive defaults; documented disable mechanism. | Planned |
| 5 | **M4 — Operator UI / Dashboard** | Expose AIOps behavior through a polished operator dashboard. | UI Hold Gate clears; dashboard refreshes data; risky actions require approval; consistent with parked `dashboard` SKILL.md. | Planned (last) |
| 6 | **M6 — Portfolio Polish** | Convert quality into visible GitHub credibility. | Reproducible KPI report; visual assets; clear 3-minute browsing story. | Planned (last) |

## KPI Targets (parent plan)

- MTTR in simulations reduced by ≥30%.
- False-positive alerts reduced by ≥25%.
- SLO burn-rate detection lead time improved by ≥20%.
- Incident scenario reproducibility ≥90%.
- Core module coverage ≥80%.

## Review Loop

After each milestone, the Claude Code agent returns: files changed and why, commands run and outcomes, test results and known gaps, risk notes, and a proposed next-milestone prompt — per the parent plan's `Review Loop` section.

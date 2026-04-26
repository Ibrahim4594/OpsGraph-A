# ADR-001: Hybrid Architecture (Python Backend + Deferred Next.js Frontend)

- **Status:** Accepted
- **Date:** 2026-04-27
- **Deciders:** Project owner (Ibrahim)

## Context

RepoPulse AIOps must combine: (a) Python-native AIOps logic (anomaly detection, correlation, recommendations) where the data-science ecosystem is strongest; and (b) a modern, accessible operator dashboard with first-class TypeScript tooling and a strong UI component ecosystem. To prevent UI churn from blocking the AIOps core, the backend is shipped first and the dashboard comes after the AIOps logic is proven.

## Decision

Adopt a hybrid monorepo: `backend/` runs FastAPI (Python 3.14). A future `frontend/` (Next.js 15 App Router, TypeScript, Tailwind v4, shadcn/ui) will land in the dedicated UI milestone after M1–M5 backend work is complete. Communication between the eventual dashboard and the backend is HTTP/JSON. Event-bus and time-series store choices are deferred to Milestone 2.

The dashboard's design system is committed up front via the `dashboard` slug pulled from `typeui.sh` (see [`docs/ui-design-system.md`](../docs/ui-design-system.md)) — the SKILL.md is parked at `.claude/skills/design-system/SKILL.md` so the design language is fixed before any UI code is written, even though no UI code lands in M1.

## Alternatives Considered

1. **Python-only with server-rendered Jinja templates** — fastest to ship but loses the operator-grade UI quality the parent plan mandates (Tailwind + shadcn + 21st components in the UI milestone).
2. **Node-only with TypeScript on both sides** — uniform stack but weaker AI/data tooling for the AIOps core.
3. **Frontend in M1 alongside backend (parent plan default)** — rejected because UI work risks consuming attention from the AIOps logic during the most uncertain milestones (M3). The parent plan's UI Hold Gate already acknowledges the same risk; pushing the UI to the end is the stricter form of that gate.

## Consequences

**Positive:** Best-of-breed tools per concern; clear blast-radius separation; CI runs the backend stack first and the frontend stack joins later in its own job; the AIOps core's correctness is provable by tests + curl + OTel UIs without waiting on a dashboard.

**Negative:** Two language toolchains long-term; the operator UI is unavailable until late in the project (mitigated by `/healthz` + curl verification, OTel UIs in M2, and CLI tooling for M3/M5 demos).

**Follow-ups:** ADR-002 (event bus choice) and ADR-003 (timeseries store) in Milestones 2–3. ADR-004 (UI architecture) when the UI milestone begins.

# SLO Specification

> **STATUS: STUB** — This document is intentionally a stub in M1. Full SLI/SLO definitions, error budget formulas, and burn-rate alert thresholds are completed in **Milestone 2** (Observability + SLO Baseline) per [`../plans/aiops-detailed-implementation-plan.md`](../plans/aiops-detailed-implementation-plan.md).

## Planned Structure (filled in M2)

The completed spec will define, for each user-visible service:

| SLI | Definition | Window | Target | Burn-Rate Alert |
|---|---|---|---|---|
| _e.g. ingest API availability_ | _ratio of 2xx/3xx responses to total_ | _30d rolling_ | _99.9%_ | _≥2× over 1h_ |
| ... | | | | |

For each SLI, M2 will document:
- **Numerator/denominator** queries (Prometheus or equivalent).
- **Window** (rolling vs calendar-aligned).
- **Target** (objective).
- **Error budget** policy and burn-rate alerting thresholds (multi-window: 1h fast, 6h slow, per Google SRE workbook).
- **Owner** (which component the SLI describes).

## Why a Stub?

The parent plan explicitly orders SLO work after the engineering baseline (M1) and before the AIOps core (M3): "make telemetry trustworthy before adding heavy AI logic." Drafting SLO numbers without the OTel collector + synthetic telemetry generator from M2 risks fabrication. This stub is intentional and labeled per the parent plan's Anti-Hallucination Protocol §3.

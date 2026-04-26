# RepoPulse AIOps

Production-grade AIOps reference project: observability, AI-assisted operations with guardrails, and measurable reliability outcomes. **Backend-first delivery** — the operator dashboard lands at the end, after the AIOps core and GitHub agentic workflows are shipped.

> Source plans live in [`plans/`](plans/). Active execution plan: [`plans/milestone-1-execution-plan.md`](plans/milestone-1-execution-plan.md). Higher-level roadmap: [`plans/aiops-detailed-implementation-plan.md`](plans/aiops-detailed-implementation-plan.md).

## Repository Layout

| Path | Purpose |
|---|---|
| [`backend/`](backend/) | FastAPI service + AIOps core (Python ≥3.11) |
| [`infra/`](infra/) | Local Docker Compose + OTel collector (M2+) |
| [`docs/`](docs/) | Architecture, SLO spec, security model, runbooks |
| [`adr/`](adr/) | Architecture Decision Records |
| [`.github/workflows/`](.github/workflows/) | Deterministic CI |

The dashboard (`frontend/`) lands in the final UI milestone, using the parked `dashboard` design skill at [`.claude/skills/design-system/SKILL.md`](.claude/skills/design-system/SKILL.md).

## Backend Bring-up

```bash
cd backend
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn repopulse.main:app --reload --port 8000
```

`curl http://localhost:8000/healthz` →

```json
{"status":"ok","service":"RepoPulse","environment":"development","version":"0.1.0"}
```

## Quality Gates

| Stack | Lint | Typecheck | Test |
|---|---|---|---|
| backend | `ruff check src tests` | `mypy` | `pytest` |

CI runs all of the above on every push and PR ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

## Status

| Order | Milestone | Scope | Status |
|---|---|---|---|
| 1 | M1 | Backend foundation | In progress |
| 2 | M2 | Observability + SLO baseline | Planned |
| 3 | M3 | AIOps core (detection / correlation / recommendations) | Planned |
| 4 | M5 | GitHub agentic workflows | Planned |
| 5 | M4 | Operator UI (dashboard) | Planned (last) |
| 6 | M6 | Portfolio polish | Planned (last) |

See [`docs/roadmap.md`](docs/roadmap.md) for milestone goals and acceptance criteria.

## Toolchain Preflight

Verified at [`docs/preflight-checklist.md`](docs/preflight-checklist.md). Required for milestone execution: Superpowers (workflow), Playwright CLI (parked for the UI milestone), Obsidian Skills (knowledge tooling), `typeui.sh` `dashboard` slug (parked for the UI milestone).

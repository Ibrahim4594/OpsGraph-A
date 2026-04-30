# Milestone 2.0 Handoff — Persistent storage (Postgres)

**Milestone:** M2.0 — SQLAlchemy async + Alembic + repository layer + async orchestrator facade  
**Date:** 2026-04-30  
**Branch:** `v2.0-storage`  
**Tag:** `v2.0.0-storage` (annotated lightweight; push when remote is configured)  
**Status:** Complete — unit gate, integration/migration jobs (CI-shaped commands), T11 legacy orchestrator removal, documentation and ADR close-out.

---

## 1. What shipped

| Area | Outcome |
|------|---------|
| **Persistence** | Postgres as system of record; async repos + `PipelineOrchestrator` session-scoped transactions. |
| **Migrations** | Alembic chain under `backend/migrations/versions/`; `scripts/db-upgrade.sh` is canonical. |
| **Dev UX** | `docker-compose.dev.yml`, `scripts/dev-stack-up.sh`, `docs/dev-stack.md`; `scripts/demo.sh` defaults `REPOPULSE_DATABASE_URL` to loopback compose Postgres. |
| **Tests** | Unit gate excludes `integration` / `e2e` / `migration`; Testcontainers-backed integration and migration suites in CI (`.github/workflows/ci.yml`). |
| **T11** | Legacy sync `pipeline/orchestrator.py` removed; `repopulse.testing.make_inmem_orchestrator` for fast async tests; `benchmark.py` async. Evidence: `m2.0-evidence/t11-legacy-removal.txt`. |
| **Docs** | `adr/ADR-006-postgres-persistent-storage.md`, `docs/operations.md`, plan path updates, README + security-model aligned with v2.0. |
| **Version** | Application version **2.0.0** (`backend/pyproject.toml`, `repopulse.__version__`, `frontend/package.json`). |

---

## 2. Commands run (verification)

| Command | Outcome |
|---------|---------|
| `pytest -m "not integration and not e2e and not migration" -q` | 296 passed, 46 deselected |
| `pytest tests/test_orchestrator.py tests/test_benchmark.py -q` | 17 passed |
| `ruff check src tests` | All checks passed |
| `mypy src tests` | Success (106 files) |

**Integration / migration / e2e** (require Docker):  
`pytest -m integration -q`, `pytest -m migration -q`, `pytest -m e2e -q` — run locally before claiming production readiness; CI runs `integration` and `migration` on `ubuntu-latest`.

---

## 3. Operator quick path

```bash
export REPOPULSE_API_SHARED_SECRET="$(openssl rand -hex 16)"
export REPOPULSE_AGENTIC_SHARED_SECRET="$(openssl rand -hex 16)"
./scripts/dev-stack-up.sh
./scripts/demo.sh
```

---

## 4. References

- Plan: `docs/superpowers/plans/milestone-2.0-storage-plan.md`
- ADR: `adr/ADR-006-postgres-persistent-storage.md`
- Ops: `docs/operations.md`
- Evidence: `docs/superpowers/plans/m2.0-evidence/` (`t1-skeleton.txt` … `t11-legacy-removal.txt`)

---

## 5. Follow-ups (out of scope for M2.0)

Per the storage plan non-goals: Arq/Redis workers (M2.1), real OTLP/GitHub ingestion (M2.2), JWT/RBAC (M3.0), SSE (M3.1), Prometheus/runbooks (M3.2), production compose hardening (M4.0).

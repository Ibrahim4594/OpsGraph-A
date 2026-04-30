# Operations — RepoPulse v2.0

Minimal runbook for anyone running the **Postgres-backed** stack in a lab or
small deployment. This is **not** a full production SRE guide (see non-goals in
`docs/superpowers/plans/milestone-2.0-storage-plan.md`).

## Prerequisites

- `REPOPULSE_DATABASE_URL` — `postgresql+psycopg://user:pass@host:port/dbname`
- `REPOPULSE_API_SHARED_SECRET` — required for protected HTTP routes
- `REPOPULSE_AGENTIC_SHARED_SECRET` — required if agentic GitHub workflows call in

All keys are defined in `backend/src/repopulse/config.py` (`Settings`).

## Schema lifecycle

```bash
# From repo root — applies Alembic migrations to the DB in DATABASE_URL
./scripts/db-upgrade.sh
```

Use the same command in CI and container entrypoints. Downgrade is supported
only where individual revisions define `downgrade()` — run
`alembic downgrade -1` with care on shared environments.

## Local / demo stack

```bash
./scripts/dev-stack-up.sh   # Postgres (+ optional api) via compose
./scripts/demo.sh           # Host uvicorn + Next after DB is up
```

Details: [`docs/dev-stack.md`](dev-stack.md).

## Health

- `GET /healthz` — liveness-style JSON including `version` and feature flags.

## Backups (Postgres)

Use your platform’s Postgres backup tooling (`pg_dump`, managed snapshots, or
PITR). **Restore drills** should include running `alembic upgrade head` after
restore if the backup predates newer migrations.

## Security

Pipeline auth, CORS, body limits, and agentic workflow trust boundaries are
documented in [`docs/security-model.md`](security-model.md) and
[`adr/ADR-005-pipeline-api-authentication.md`](../adr/ADR-005-pipeline-api-authentication.md).

## Where to look in code

| Concern | Location |
|--------|----------|
| Async orchestrator facade | `backend/src/repopulse/pipeline/async_orchestrator.py` |
| Engine + session factory | `backend/src/repopulse/db/engine.py` |
| Repositories | `backend/src/repopulse/db/repository/` |
| ORM models | `backend/src/repopulse/db/models/` |
| Migrations | `backend/migrations/versions/` |
| In-memory test harness | `backend/src/repopulse/testing/` |

## Further reading

- [`adr/ADR-006-postgres-persistent-storage.md`](../adr/ADR-006-postgres-persistent-storage.md)
- [`docs/SETUP.md`](SETUP.md)
- [`docs/architecture.md`](architecture.md)

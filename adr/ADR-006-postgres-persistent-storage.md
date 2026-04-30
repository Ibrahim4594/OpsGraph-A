# ADR-006 — Postgres persistent storage for the AIOps pipeline

## Status

Accepted (v2.0.0 — storage milestone)

## Context

Through v1.1.0 the reference implementation kept pipeline state (events,
anomalies, incidents, recommendations, action history, workflow usage) in
process memory inside `PipelineOrchestrator`. That was correct for demos and
fast unit tests, but it prevented restart-safe operation, horizontal scaling,
and serious evaluation of retention, replay, and operational backup/restore.

Milestone 2.0 replaces that default with **Postgres** accessed through
**SQLAlchemy 2.x async** sessions, **repository** objects per aggregate, and
**Alembic** migrations. The **HTTP API contract** (routes, JSON shapes, auth,
approval gate) stays stable: callers should not see a breaking change at the
edge.

## Decision

1. **Primary store** — Postgres 16+ is the system of record for all pipeline
   aggregates listed in the milestone-2.0 schema (raw events through workflow
   usage).
2. **Async SQLAlchemy** — `AsyncEngine` + `async_sessionmaker`; repositories
   accept an `AsyncSession`; the orchestrator owns transaction boundaries.
3. **Alembic** — Forward migrations live under `backend/migrations/versions/`;
   `scripts/db-upgrade.sh` wraps `alembic upgrade head` for operators and CI.
4. **Configuration** — `REPOPULSE_DATABASE_URL` (see `Settings.database_url`)
   uses the `postgresql+psycopg://...` scheme. If unset **and** no test
   orchestrator is injected, `create_app()` **raises** at import/setup time so
   production never silently runs without persistence.
5. **Testing split** — Default `pytest` gate (CI `backend` job) excludes
   `integration`, `e2e`, and `migration` markers for speed. **Testcontainers**
   Postgres backs `pytest -m integration` and `pytest -m migration`; see
   `backend/tests/integration/conftest.py`.
6. **Legacy removal (T11)** — The synchronous in-process `pipeline/orchestrator`
   module was removed. Production and DB integration use
   `repopulse.pipeline.async_orchestrator.PipelineOrchestrator`. Local/unit
   tests use `repopulse.testing.make_inmem_orchestrator()` so the suite stays
   fast without Docker.

## Consequences

- **Demo / local** — `./scripts/demo.sh` requires Postgres reachable at the
  default loopback DSN (see `scripts/demo.sh` and `docs/dev-stack.md`).
- **Ops** — Backups, replication, and connection pooling are standard Postgres
  concerns; see `docs/operations.md` for a minimal runbook.
- **Rollback** — Application rollback to v1.1.x is a separate concern from
  **data** already written under v2 migrations; document downgrade paths per
  migration where reversible.

## Alternatives considered

- **SQLite for dev** — Rejected for integration fidelity (Postgres-specific
  types and behavior).
- **ORM-free raw SQL** — Possible later; rejected for maintainability at this
  milestone.
- **Keep dual sync/async orchestrators** — Rejected (T11); one async facade
  plus an explicit in-memory test harness only.

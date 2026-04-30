# Milestone 2.0 — Persistent storage (Postgres + SQLAlchemy async + Alembic)

**Status: Shipped.** Handoff: [`milestone-2.0-handoff.md`](milestone-2.0-handoff.md) · Tag **`v2.0.0-storage`** · ADR: [`../../../adr/ADR-006-postgres-persistent-storage.md`](../../../adr/ADR-006-postgres-persistent-storage.md).
> Baseline: `v1.1.0`. Primary branch for this work: `v2.0-storage`.

## Goal

Replace the in-memory `PipelineOrchestrator` deques with a Postgres-backed
storage layer. **API surface and existing behaviour are preserved**: every
HTTP route, every recommendation rule, every audit-history field stays the
same from a caller's perspective. The orchestrator becomes a thin facade
that delegates to repository objects.

## Non-goals (deferred)

| Concern | Goes in |
|---|---|
| Async/queue worker model (Arq + Redis) | M2.1 |
| Real OTLP / GitHub-webhook ingestion | M2.2 |
| JWT + RBAC operator sessions | M3.0 |
| SSE realtime fan-out | M3.1 |
| Prometheus + readyz + ops runbooks | M3.2 |
| Production compose + CI hardening | M4.0 |

## Tech choices (already approved per D4/D7/D10)

- **D4** — SQLAlchemy 2.x async (`sqlalchemy[asyncio]>=2.0`)
- **D7** — Alembic migrations
- **D10** — Testcontainers Postgres (preferred); CI fallback to local Postgres
  service. **No SQLite shortcuts** for integration behavior.
- New runtime deps: `psycopg[binary,pool]>=3.2`, `sqlalchemy[asyncio]>=2.0`,
  `alembic>=1.13`. Test-only: `testcontainers[postgres]>=4.0`.

---

## 1. SQLAlchemy async model layout + repository boundaries

### 1.1 Package layout

```
backend/src/repopulse/
├── db/                              ← NEW package
│   ├── __init__.py
│   ├── engine.py                    AsyncEngine factory + session maker
│   ├── base.py                      DeclarativeBase + naming convention
│   ├── models/
│   │   ├── __init__.py              re-export every ORM model
│   │   ├── raw_event.py             RawEventORM      (idempotency anchor)
│   │   ├── normalized_event.py      NormalizedEventORM
│   │   ├── anomaly.py               AnomalyORM
│   │   ├── incident.py              IncidentORM
│   │   ├── recommendation.py        RecommendationORM (+ state column)
│   │   ├── recommendation_transition.py  RecommendationTransitionORM
│   │   ├── action_history.py        ActionHistoryORM
│   │   └── workflow_usage.py        WorkflowUsageORM
│   └── repository/
│       ├── __init__.py
│       ├── base.py                  generic Repository[T] protocol
│       ├── event_repo.py
│       ├── anomaly_repo.py
│       ├── incident_repo.py
│       ├── recommendation_repo.py
│       ├── action_history_repo.py
│       └── workflow_usage_repo.py
├── pipeline/
│   └── async_orchestrator.py        MODIFIED — facade calls repos via DI
├── api/                             unchanged route-level
└── config.py                        +database_url, +database_pool_*
```

### 1.2 Repository contract

Each repo is a small async class scoped to one aggregate. Pattern:

```python
# repopulse/db/repository/base.py
class Repository(Protocol):
    """Marker; concrete repos define their own ops because aggregates differ."""

# repopulse/db/repository/recommendation_repo.py
class RecommendationRepository:
    def __init__(self, session: AsyncSession) -> None: ...

    async def insert(self, rec: Recommendation) -> None: ...
    async def list_latest(self, limit: int) -> list[Recommendation]: ...
    async def find_by_id(self, rec_id: UUID) -> Recommendation | None: ...
    async def update_state(
        self, rec_id: UUID, *, to_state: State, actor: str, reason: str | None
    ) -> Recommendation: ...
```

Key rules:

- Repos **never** call other repos. The orchestrator (or future service
  layer) composes them.
- Repos return **domain dataclasses** (the existing
  `Recommendation`, `Incident`, `Anomaly`, `NormalizedEvent`, `ActionHistoryEntry`)
  built from ORM rows. ORM types do not leak into the API or tests.
- All operations take an `AsyncSession`. Transaction boundaries are owned by
  the caller (orchestrator), not the repo.

### 1.3 Domain ↔ ORM mapping

| Domain dataclass | Source | ORM table | Notes |
|---|---|---|---|
| `EventEnvelope` | `repopulse.api.events` | `raw_events` | persists pre-normalize for replay/forensics; `event_id` UNIQUE for idempotency |
| `NormalizedEvent` | `repopulse.pipeline.normalize` | `normalized_events` | `received_at`, `occurred_at` indexed; `attributes` jsonb |
| `Anomaly` | `repopulse.anomaly.detector` | `anomalies` | `series_name`, `timestamp` indexed |
| `Incident` | `repopulse.correlation.engine` | `incidents` | `started_at`, `ended_at` indexed |
| (assoc) | — | `incident_events`, `incident_anomalies` | many-to-many bridge tables |
| `Recommendation` | `repopulse.recommend.engine` | `recommendations` | `state` column + index; `evidence_trace` jsonb |
| (transition log) | — | `recommendation_transitions` | append-only; one row per state change |
| `ActionHistoryEntry` | `repopulse.pipeline.types` | `action_history` | `at` indexed |
| `WorkflowUsage` | `repopulse.github.usage` | `workflow_usage` | `run_id` UNIQUE per repository |

### 1.4 Orchestrator facade (skeleton — code goes in M2.0 task 5)

```python
# repopulse/pipeline/async_orchestrator.py — POST-M2.0 (async facade; legacy sync module removed in T11)
class PipelineOrchestrator:
    def __init__(
        self, *,
        session_maker: async_sessionmaker[AsyncSession],
        recs_repo_factory: Callable[[AsyncSession], RecommendationRepository],
        # ... one factory per repo
    ) -> None: ...

    async def ingest(self, env: EventEnvelope, *, received_at: datetime) -> NormalizedEvent:
        async with self._session_maker.begin() as session:
            await self._events_repo(session).insert_idempotent(env, received_at)
            normalized = normalize(env, received_at=received_at)
            await self._normalized_repo(session).insert(normalized)
            return normalized

    async def evaluate(self, *, window_seconds: float = 300.0) -> list[Recommendation]:
        async with self._session_maker.begin() as session:
            events = await self._normalized_repo(session).list_recent()
            anomalies = await self._anomaly_repo(session).list_recent()
            incidents = correlate(anomalies=anomalies, events=events,
                                  window_seconds=window_seconds)
            new_recs: list[Recommendation] = []
            for inc in incidents:
                key = _incident_key(inc)
                if not await self._incidents_repo(session).register_key(key):
                    continue
                await self._incidents_repo(session).insert(inc)
                rec = recommend(inc)
                await self._recs_repo(session).insert(rec)
                if rec.state == "observed":
                    await self._action_history_repo(session).insert(
                        ActionHistoryEntry(at=now_utc(), kind="observe",
                                           recommendation_id=rec.recommendation_id,
                                           actor="system",
                                           summary="R1 fallback: auto-observed"))
                new_recs.append(rec)
            return new_recs
```

The synchronous public methods (`latest_recommendations`, `record_anomalies`,
`transition_recommendation`, etc.) wrap the async impl with `asyncio.run`
**only** at the API layer that's still sync (FastAPI sync handlers); the
orchestrator itself is async-first. Actual sync/async boundary work is
in M2.0 task 5.

### 1.5 What stays in-memory

- The M3 incident **content-signature dedup set** (`_seen_keys`) — moves to
  a `incident_signatures` table with UNIQUE constraint, no separate set
  needed.
- The M4 `_rec_state` overlay dict — replaced by the `state` column on
  `recommendations`.
- The M4 bounded action-history deque — replaced by a query with `LIMIT`.
  No more "drop oldest" behavior; rows persist forever (they're append-only
  audit). Documented as a behavior change in §3 below.

---

## 2. Alembic migration sequence

Migrations are kept short and **explicit** — no Alembic autogenerate
shortcuts. Every revision lands one logical change so rollback is single-step.

| Rev | File | Up | Down |
|---|---|---|---|
| `0001_initial_schema` | `migrations/versions/0001_initial_schema.py` | Create `raw_events`, `normalized_events` (FK→raw_events.event_id), `anomalies`, `incidents` (incl. `signature_hash` + UNIQUE), `incident_events`, `incident_anomalies`, `recommendations`, `action_history`, `workflow_usage` with NOT NULL columns and PK constraints. Idempotency on `raw_events` is the PK on `event_id` itself — no separate UNIQUE constraint needed. | `DROP TABLE` in reverse FK order |
| `0002_recommendation_state` | `migrations/versions/0002_recommendation_state.py` | Add `recommendations.state` (CHECK constraint: pending/approved/rejected/observed); set NOT NULL with default `'pending'`; backfill row-default on existing rows (zero rows on a fresh DB; defensive on later upgrade paths) | DROP COLUMN |
| `0003_indexes_hot_paths` | `migrations/versions/0003_indexes_hot_paths.py` | `CREATE INDEX` on `(received_at)` for `normalized_events`; `(timestamp, series_name)` for `anomalies`; `(started_at)` and `(ended_at)` for `incidents`; `(state, action_category)` for `recommendations`; `(at)` for `action_history`; `(run_id, repository)` UNIQUE for `workflow_usage` | DROP INDEX in reverse |
| `0004_recommendation_transitions` | `migrations/versions/0004_recommendation_transitions.py` | Create `recommendation_transitions` (id PK, recommendation_id FK, from_state, to_state, actor, reason, at); index on `(recommendation_id, at)` | DROP TABLE + index |
| `0005_incident_signature_dedup` | `migrations/versions/0005_incident_signature_dedup.py` | **Existing-deployment-only DDL**: `ADD COLUMN incidents.signature_hash` + backfill (deterministic hash of `_incident_key` over existing rows) + UNIQUE INDEX. Fresh databases (CI, dev, brand-new prod) get the column from migration `0001` directly — `0005` is a no-op there. The model in `db/models/incident.py` is the source of truth. | DROP INDEX + DROP COLUMN |

**Naming convention** in `db/base.py` so Alembic-generated names are stable
across environments:

```python
metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)
```

**Migration runner**: `alembic upgrade head` is run by:
1. `scripts/db-upgrade.sh` for local dev.
2. The `api` container's entrypoint *before* uvicorn starts (M2.0 task 9).
3. CI: a dedicated job `migrations` that boots a Postgres service, runs
   `alembic upgrade head`, then `alembic downgrade -1` and `alembic upgrade head`
   to verify reversibility.

---

## 3. Data migration / backfill strategy from in-memory assumptions

The in-memory model has **three implicit assumptions** that the persistent
model must explicitly address:

### 3.1 No persisted history → fresh schema

Today's orchestrator starts every process with empty deques. There is **no
existing data** to migrate. The "migration" is therefore the schema creation
itself (migration `0001`). Production deployments running v1.1.0 today
will start with an empty DB and re-populate on traffic.

Behavior change: a process restart no longer loses incidents/recommendations.
Documented in the M2.0 handoff §"Behavior changes".

### 3.2 Bounded deques → unbounded tables

Old:
- `_events`: `deque(maxlen=1000)`
- `_anomalies`: `deque(maxlen=200)`
- `_incidents`: `deque(maxlen=100)`
- `_recommendations`: `deque(maxlen=50)`
- `_action_history`: `deque(maxlen=200)`

New: rows are append-only and capped only by Postgres / disk.

**Mitigation in M2.0**: read APIs (`latest_recommendations(limit)`, etc.)
keep their `LIMIT` parameter — defaults match the old `maxlen` so the
dashboard pagination feels identical. The orchestrator adds a
`prune(older_than: timedelta)` operation that's wired up in M3.2 (ops
runbooks) for retention; in M2.0 it exists but is not scheduled.

### 3.3 In-memory dedup state → persistent UNIQUE

Old: `_seen_keys` set + LRU deque on the orchestrator.
New: `incidents.signature_hash` column with UNIQUE constraint.

Insertion uses `INSERT ... ON CONFLICT (signature_hash) DO NOTHING RETURNING`.
If `RETURNING` returns nothing, the incident was a duplicate and no new
recommendation is emitted — same observable behavior as v1.1.

### 3.4 Replay tooling

`backend/src/repopulse/scripts/replay_from_jsonl.py` (new in M2.0 task 8):
reads a JSONL file of `EventEnvelope` records and POSTs them against a
running backend. Used to rebuild a known dataset against a fresh DB
during development, and to replay captured production payloads (when those
exist after M2.2).

The benchmark scenarios (`scenarios/*.json`) keep working unchanged because
`benchmark.py` uses an in-process orchestrator with a temporary
`SQLAlchemyContainer.start_async()` test database (see §4.3).

---

## 4. Test plan

### 4.1 Unit tests (in-memory, fast)

Stay where they are. The dataclass-level tests of `normalize`, `correlate`,
`recommend`, anomaly detector, and SLO module **do not need Postgres**.

| File | Status |
|---|---|
| `test_normalize.py`, `test_correlation.py`, `test_recommend.py`, `test_anomaly_detector.py`, `test_slo.py`, `test_load_generator.py`, `test_telemetry.py`, `test_health.py`, `test_cors_safety.py`, `test_body_size_limit.py`, `test_auth_negative_paths.py`, `test_github_*.py`, `test_benchmark.py`, `test_scenarios.py` | unchanged |

### 4.2 Integration tests (Testcontainers Postgres)

A new `backend/tests/conftest.py` fixture spins up a Postgres container
once per session, applies migrations, and yields an `AsyncEngine`. Each
test gets a fresh transaction that's rolled back at teardown — so tests
share the schema but never share data.

```python
# backend/tests/integration/conftest.py
@pytest.fixture(scope="session")
def postgres_url() -> str:
    if os.getenv("REPOPULSE_TEST_DATABASE_URL"):
        return os.environ["REPOPULSE_TEST_DATABASE_URL"]      # CI fallback
    with PostgresContainer("postgres:16-alpine") as pg:        # default
        yield pg.get_connection_url().replace("postgresql://", "postgresql+psycopg://")

@pytest_asyncio.fixture(scope="session")
async def engine(postgres_url: str) -> AsyncEngine:
    engine = create_async_engine(postgres_url, future=True)
    await alembic_upgrade_head(engine)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncSession:
    async with engine.connect() as conn:
        async with conn.begin() as trans:
            session = AsyncSession(bind=conn, expire_on_commit=False)
            yield session
            await trans.rollback()
```

| File | Coverage |
|---|---|
| `tests/integration/test_event_repo.py` | NEW — insert + idempotent re-insert + list_recent |
| `tests/integration/test_anomaly_repo.py` | NEW — insert batch + list_recent + window query |
| `tests/integration/test_incident_repo.py` | NEW — insert + signature dedup + many-to-many bridges |
| `tests/integration/test_recommendation_repo.py` | NEW — insert + list_latest + state transitions + 409 on illegal |
| `tests/integration/test_action_history_repo.py` | NEW — append-only + filter by kind + LIMIT |
| `tests/integration/test_workflow_usage_repo.py` | NEW — insert + run_id-per-repo unique |
| `tests/integration/test_orchestrator_db_facade.py` | NEW — full pipeline (ingest → evaluate → transition) against real DB |

Existing `test_orchestrator.py` is **rewritten** to drive the new facade
via Testcontainers; the old in-memory version is **deleted** (no parallel
implementations). Behavior assertions remain identical to ensure the
M2.0 facade preserves observable behavior.

### 4.3 End-to-end tests (FastAPI + Testcontainers)

| File | Coverage |
|---|---|
| `tests/e2e/test_pipeline_e2e_db.py` | NEW — POST /events → GET /recommendations against real DB; restart-survival check |
| `tests/e2e/test_approve_reject_e2e.py` | NEW — POST /approve writes a `recommendation_transitions` row; GET /actions returns the transition |
| `tests/e2e/test_dedup_e2e.py` | NEW — POST same EventEnvelope twice → only one `raw_events` row; same incident signature → only one recommendation |

`test_pipeline_e2e.py` (existing M3 test) is rewritten to use the DB
facade. Behavior assertions identical.

### 4.4 Migration tests

| File | Coverage |
|---|---|
| `tests/migrations/test_alembic_reversible.py` | NEW — for each rev in 0001→0005, run upgrade then downgrade; assert no schema drift via `inspect(engine)` |
| `tests/migrations/test_migration_runs_clean.py` | NEW — `alembic upgrade head` on an empty DB exits 0 and produces all expected tables/indexes |

### 4.5 Frontend

No frontend changes in M2.0. Existing 53 vitest specs remain green.

---

## 5. Rollback plan per migration

Every migration is reversible. The general rollback flow is the same:
`alembic downgrade -1` for one step back, or `alembic downgrade <rev>`
to a specific revision. Below is the **per-migration consequence** so
the operator knows what happens to running data.

| Rev | Forward effect | Reverse effect | Data loss? |
|---|---|---|---|
| 0001 | Creates 10 tables (9 named aggregates + the 2 bridge tables — `incident_events` and `incident_anomalies` — count as one schema-level pair); `incidents.signature_hash` + UNIQUE included from the start | Drops every table in reverse FK order | **YES** — all rows lost. Only run on a deployment you intend to wipe. Operator runbook in M3.2 will warn explicitly. |
| 0002 | Defensive `ADD COLUMN recommendations.state` (NOT NULL default `pending`) + CHECK — guarded by `IF NOT EXISTS`, so no-op on fresh v2.0 DBs (the column is already there from 0001) | **No-op on fresh DBs** (column owned by 0001). Older deployments where this rev added the column must drop it manually after a `pg_dump`. | NO on fresh DBs (downgrade is a documented no-op). YES on older deployments where this rev did the work — but `0002 downgrade` doesn't perform the drop automatically; operator action required. |
| 0003 | Defensive `CREATE INDEX IF NOT EXISTS` for the dashboard hot paths + UNIQUE on workflow_usage — no-op on fresh v2.0 DBs | **No-op on fresh DBs** (indexes owned by 0001). | NO. Performance regression only on older deployments where downgrading manually drops these indexes. |
| 0004 | Defensive `CREATE TABLE IF NOT EXISTS recommendation_transitions` — no-op on fresh v2.0 DBs | **No-op on fresh DBs** (table owned by 0001). Older deployments that created the table here must drop it manually after a snapshot. | NO on fresh DBs. YES on older deployments where this rev did the work — operator action required. |
| 0005 | Existing-deployment-only `ADD COLUMN incidents.signature_hash` + backfill (md5-derived placeholder) + UNIQUE — no-op on fresh v2.0 DBs (column owned by 0001) | **No-op on fresh DBs** (column owned by 0001). Older deployments must drop the column manually after a snapshot — and re-establish in-memory dedup, which is gone in v2.0. | NO on fresh DBs. Reverts dedup invariant on older deployments — operator must script the manual drop with care. |

**Application rollback (binary level)**: `git checkout v1.1.0` recovers the
in-memory orchestrator. The DB can stay populated; the in-memory v1.1
binary simply ignores it. Forward-rolling back to v2.0 will pick up the
existing data.

**CI verifies reversibility**: `tests/migrations/test_alembic_reversible.py`
runs upgrade → downgrade → upgrade for each rev, so any non-reversible
migration fails the build before it can ship.

**Backup discipline**: production deploys must take a `pg_dump` snapshot
before running migration 0001 (the only rev with unavoidable data loss
on rollback) and before any **manual** drops the operator performs to
revert 0002, 0004, or 0005 on older deployments. Defensive
revisions 0002–0005 do **not** drop objects they did not create on
fresh DBs — their `downgrade()` callables are intentional no-ops. The
deploy script in M4.0 wires the snapshot step in; until then it is
documented in `docs/operations.md` (M3.2).

---

## 6. Acceptance gates / commands

Every M2.0 task adds tests; the milestone is "done" only when **every gate
exits 0** and the captured outputs are committed under
`docs/superpowers/plans/m2.0-evidence/`.

### 6.1 Backend gates

```bash
cd backend

# Unit tests (no DB)
./.venv/Scripts/python -m pytest -m "not integration and not e2e and not migration" -q
# Expected: 250+ passed, 0 failed.   (was 236 in v1.1.0; +14 from the new repo unit tests)

# Integration tests (Testcontainers Postgres — requires Docker)
./.venv/Scripts/python -m pytest -m integration -q
# Expected: ~30 passed across 7 integration test files, 0 failed.

# End-to-end tests
./.venv/Scripts/python -m pytest -m e2e -q
# Expected: 3 e2e tests passed, 0 failed.

# Migration reversibility
./.venv/Scripts/python -m pytest -m migration -q
# Expected: 2 migration tests passed (one per file), 0 failed.

# Lint + type
./.venv/Scripts/python -m ruff check src tests
# Expected: All checks passed!
./.venv/Scripts/python -m mypy
# Expected: Success: no issues found in 80+ source files

# Migration runs clean against an empty DB (smoke check, separate from pytest)
docker run --rm -d --name repopulse-pg-smoke -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:16-alpine
sleep 3
REPOPULSE_DATABASE_URL=postgresql+psycopg://postgres:test@localhost:55432/postgres \
  ./.venv/Scripts/python -m alembic upgrade head
# Expected: "Running upgrade ... -> 0005_incident_signature_dedup"
docker rm -f repopulse-pg-smoke
```

### 6.2 Frontend gates (unchanged)

```bash
cd frontend
npm test                  # → Tests 53 passed (11 files)
npm run typecheck         # → exit 0
npm run build             # → Compiled successfully; First Load JS <= 200 kB on every route
```

### 6.3 End-to-end smoke against the real demo stack

`docker compose -f docker-compose.dev.yml up -d postgres` (new in M2.0
task 9) brings up Postgres on localhost:5432. Then:

```bash
export REPOPULSE_DATABASE_URL=postgresql+psycopg://repopulse:repopulse@localhost:5432/repopulse
export REPOPULSE_API_SHARED_SECRET=$(openssl rand -hex 16)
export REPOPULSE_AGENTIC_SHARED_SECRET=$(openssl rand -hex 16)
./scripts/demo.sh
# Expected: backend logs "Database ready (alembic head: 0005_incident_signature_dedup)"
#           dashboard at http://localhost:3000 shows seeded data
#           kill demo, restart it: data SURVIVES (proof of persistence)
```

### 6.4 Total expected test count post-M2.0

| Layer | v1.1.0 | M2.0 target |
|---|---|---|
| Backend unit | 236 | ~250 (existing + small repo unit tests) |
| Backend integration (DB) | 0 | ~30 |
| Backend e2e (DB-backed) | 0 | 3 |
| Backend migrations | 0 | 2 |
| Frontend | 53 | 53 (unchanged) |
| **Total** | **289** | **~338** |

---

## Task list (file-by-file, ordered for incremental commits)

| # | Task | New files | Modified files |
|---|---|---|---|
| 1 | Add deps + Alembic skeleton | `backend/migrations/env.py`, `backend/migrations/script.py.mako`, `backend/alembic.ini` | `backend/pyproject.toml` |
| 2 | `db/base.py` + `db/engine.py` + `Settings.database_url` | `db/__init__.py`, `db/base.py`, `db/engine.py` | `backend/src/repopulse/config.py` |
| 3 | ORM models (one file per aggregate, 8 files) | `db/models/*.py` | — |
| 4 | Repositories (6 files) | `db/repository/*.py` | — |
| 5 | Orchestrator facade rewrite | — | `pipeline/async_orchestrator.py` |
| 6 | Wire `app.state.session_maker` | — | `main.py` |
| 7 | Migrations 0001–0005 | `migrations/versions/0001..0005_*.py` | — |
| 8 | Replay tooling | `backend/src/repopulse/scripts/replay_from_jsonl.py` | — |
| 9 | Compose: add Postgres service | `docker-compose.dev.yml` | `scripts/demo.sh` (export DATABASE_URL) |
| 10 | Tests: integration conftest + 7 repo tests | `tests/integration/conftest.py`, `tests/integration/test_*.py` | — |
| 11 | Tests: e2e (3 files) + migrations (2 files) | `tests/e2e/test_*.py`, `tests/migrations/test_*.py` | `pyproject.toml` (pytest markers) |
| 12 | Rewrite `test_orchestrator.py` + `test_pipeline_e2e.py` against DB facade | — | both files |
| 13 | Docs + ADR | `adr/ADR-006-postgres-storage.md`, `docs/operations.md` (skeleton) | `docs/SETUP.md`, `docs/security-model.md` (database-url note) |
| 14 | Verification + handoff + tag `v2.0.0-storage` | `docs/superpowers/plans/milestone-2.0-handoff.md`, `m2.0-evidence/` | — |

Each task lands one commit. After task 7 the schema is in; after task 12 the
test suite is fully green against the new layer; tasks 13–14 are the
close-out.

---

## Stop point

**The next step is task 1 (add deps + Alembic skeleton).** I will not
touch any DB code until you reply with one of:

- **"Approved — execute M2.0 task by task."**
- **"Approved with changes: §X = …"**
- **"Hold — let's discuss [topic]."**

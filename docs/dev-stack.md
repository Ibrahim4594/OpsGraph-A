# Dev stack — Postgres + backend via Docker Compose

M2.0 T9 ships a `docker-compose.dev.yml` that brings up the v2.0 storage
backend (`postgres:16-alpine`) and the FastAPI app behind it, both
bound to loopback. This is the canonical local-dev path; the host venv
+ host uvicorn pattern still works (see *Hybrid mode* below).

## Prerequisites

```bash
export REPOPULSE_API_SHARED_SECRET="$(openssl rand -hex 16)"
export REPOPULSE_AGENTIC_SHARED_SECRET="$(openssl rand -hex 16)"
```

Both are mandatory — `docker-compose.dev.yml` declares them with
`${VAR:?...}` so missing values fail loudly at config time.

## Operator runbook

```bash
# 1) Bring up Postgres + the api container, run migrations.
#    Idempotent — re-running on an already-up stack is a no-op.
./scripts/dev-stack-up.sh

# 2) Run migrations explicitly (also runs at api container startup).
./scripts/db-upgrade.sh

# 3) Smoke-test the API.
curl http://127.0.0.1:8000/healthz
# {"status":"ok","service":"RepoPulse",...}

# 4) Stop the stack — preserves the Postgres data volume.
docker compose -f docker-compose.dev.yml down

# 5) Stop AND wipe Postgres data (full reset).
docker compose -f docker-compose.dev.yml down -v
```

## What the compose file declares

| Service    | Image                | Bind                | Notes                                            |
|------------|----------------------|---------------------|--------------------------------------------------|
| `postgres` | `postgres:16-alpine` | `127.0.0.1:${POSTGRES_HOST_PORT:-55432}` | Persistent volume `repopulse_pgdata`; healthcheck via `pg_isready`. Override `POSTGRES_HOST_PORT` to dodge clashes with other local stacks. |
| `api`      | built from `backend/Dockerfile` | `127.0.0.1:8000` | `depends_on: postgres: condition: service_healthy` — waits on real DB readiness, not just container start. Runs `alembic upgrade head` on entry, then uvicorn. |

The `REPOPULSE_DATABASE_URL` baked into the api service is:

```
postgresql+psycopg://repopulse:repopulse@postgres:5432/repopulse
```

— `postgres` is the compose-network hostname. From the host (psql,
host-side alembic, the demo script, the replay tool), use the
loopback-exposed port:

```
postgresql+psycopg://repopulse:repopulse@127.0.0.1:55432/repopulse
```

`scripts/db-upgrade.sh` and `scripts/demo.sh` default to that DSN; both
honor a pre-set `REPOPULSE_DATABASE_URL` override.

## Hybrid mode (host venv + compose Postgres)

Most dev-loop time goes to backend code; rebuilding the api container
on every edit is wasteful. The hybrid pattern: only Postgres in compose,
backend on the host venv.

```bash
# Bring up only postgres
docker compose -f docker-compose.dev.yml up -d postgres

# Run the host backend
export REPOPULSE_DATABASE_URL="postgresql+psycopg://repopulse:repopulse@127.0.0.1:55432/repopulse"
./scripts/db-upgrade.sh
./scripts/demo.sh   # boots backend (host) + frontend, seeds demo data
```

`scripts/demo.sh` runs migrations and exports `REPOPULSE_DATABASE_URL`
for uvicorn — no extra steps required as long as you've exported the
two API secrets.

## Production password rotation

The compose file's hard-coded password (`repopulse / repopulse`) is
intentionally weak — it lives in the repo and only protects a
volume that lives on a developer's laptop. Production (M4.0) wires
secrets through the orchestrator's secret store; do **not** copy this
DSN into a deployment.

## Wipe-and-recreate

Schema corruption during a refactor? Quickest path:

```bash
docker compose -f docker-compose.dev.yml down -v
./scripts/dev-stack-up.sh
```

This destroys all Postgres data and re-runs migrations from `0001` on a
clean DB. The named volume `repopulse_pgdata` is removed by `down -v`.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `db-upgrade.sh: connection refused` | Postgres container hasn't reached healthy state yet | wait ~5s and retry, or run `./scripts/dev-stack-up.sh` which waits explicitly |
| `REPOPULSE_API_SHARED_SECRET is required` from `docker compose` | env var unset | export the two API secrets before running compose |
| `port 8000 already in use` | host backend already running outside compose | stop the host process or set `PORT_BACKEND=8011 ./scripts/demo.sh` |
| `pytest -m migration -q` skips everything | Docker daemon not reachable | start Docker Desktop, then re-run |

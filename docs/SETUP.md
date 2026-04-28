# Setup

## What you actually need

**Required:** Python 3.11+, Node.js 20+, Git. You can develop entirely on **native Windows** (PowerShell + `backend\.venv`) or macOS/Linux — the same commands work; CI uses `ubuntu-latest` on GitHub, so you do **not** need a local Linux machine for correctness.

**Optional:** Docker + WSL Ubuntu only if you want the **OTel Collector** stack from `infra/` or you prefer Linux-native tooling. They are **not** required for `pytest`, `npm test`, or `./scripts/demo.sh` (Git Bash/WSL recommended for the bash demo script only because it is `.sh`).

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | 3.11+ | backend (FastAPI 0.136, pydantic 2.13) |
| Node.js | 20+ LTS | frontend (Next.js 15) |
| Docker | any current | OTel Collector (**optional**, only for telemetry validation runs) |
| Git | any | source control |

## Path A — WSL Ubuntu LTS (recommended on Windows)

If you have **Docker Desktop linked with WSL Ubuntu LTS** (the most common
working setup on Windows), you already have Docker. Add the rest:

```bash
# In your WSL Ubuntu shell:
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip git
```

Ubuntu 22.04 LTS ships Node 12; Ubuntu 24.04 LTS ships Node 18. Both are
too old for Next.js 15. Install Node 20 LTS via [nvm](https://github.com/nvm-sh/nvm):

```bash
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/master/install.sh | bash
# reload your shell, then:
nvm install --lts
nvm use --lts
node --version    # → v20.x
```

## Path B — Native Windows / macOS / other Linux

Install Python 3.11+, Node 20+ LTS, Docker, and Git from your platform's
preferred channels (homebrew, winget, apt, etc.).

## Backend

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate          # Windows cmd: .venv\Scripts\activate
pip install -e ".[dev]"
# v1.1: pipeline routes need a shared secret (tests set this via conftest).
export REPOPULSE_API_SHARED_SECRET="your-local-secret"
pytest                              # run ``pytest --co -q`` for current count
```

If you omit `REPOPULSE_API_SHARED_SECRET`, protected routes return **503** at
runtime (fail closed). Use a disposable value for local work.

The `simulate_error` flag on `POST /api/v1/events` (used by the load
generator and a few tests) is **disabled by default** in v1.1. To enable
it for a synthetic-load run:

```bash
export REPOPULSE_ALLOW_SIMULATE_ERROR=true
```

Leaving it `false` (the default) returns **403** for any ingest carrying
`simulate_error: true`, which is the right behaviour for production.

## Frontend

```bash
cd frontend
npm install
npm test                            # vitest; see test output for count
npm run build                       # production build (under 200 KB First Load JS)
```

For the operator UI to call a backend on another origin during development,
either:

1. **CORS allowlist (implemented)** — set `REPOPULSE_CORS_ORIGINS` to the
   exact browser origin(s), e.g. `http://127.0.0.1:3000`, and pass the pipeline
   bearer via `NEXT_PUBLIC_API_SHARED_SECRET` (demo/lab only), or
2. **Next.js BFF (not implemented here)** — add Route Handlers that attach
   `Authorization` server-side so the browser never holds the pipeline secret.

`scripts/demo.sh` uses (1) with loopback bind on both processes.

## Database (M2.0+)

The storage layer (M2.0) introduces Postgres as the primary persistent
store. Until M2.0 task 7 ships migrations, the only requirement is
`REPOPULSE_DATABASE_URL` — Alembic refuses to run without it:

```bash
# Local dev (Postgres on host:5432):
export REPOPULSE_DATABASE_URL="postgresql+psycopg://repopulse:repopulse@localhost:5432/repopulse"
```

The dev compose file (M2.0 task 9) provides a matching Postgres service.
Tests that need a database use Testcontainers Postgres by default — no
extra setup required if Docker is available; CI may set
`REPOPULSE_TEST_DATABASE_URL` to point at a service container instead.

## OTel Collector (optional)

The backend works without the collector — telemetry goes to console
exporters by default. If you want real OTLP export, start the collector:

```bash
cd infra
docker compose up -d otel-collector
```

This pulls `otel/opentelemetry-collector-contrib:0.116.1` and listens on
`localhost:4317` (gRPC) and `localhost:4318` (HTTP).

## One-command demo

Requires **strong** secrets (the script exits if they are missing). On
Windows, run from **Git Bash** / WSL (script is bash), or set the variables
in PowerShell using e.g.
`python -c "import secrets; print(secrets.token_hex(16))"` twice.

```bash
export REPOPULSE_API_SHARED_SECRET="$(openssl rand -hex 16)"
export REPOPULSE_AGENTIC_SHARED_SECRET="$(openssl rand -hex 16)"
./scripts/demo.sh
```

Boots backend + frontend on **127.0.0.1**, exports CORS for the chosen
frontend port, sets `NEXT_PUBLIC_API_SHARED_SECRET` to match the pipeline
secret, and seeds data. See [docs/demo/README.md](demo/README.md) and
[security-model.md](security-model.md).

## Verify everything works

```bash
# Backend (from repo root)
cd backend && pytest && ruff check src tests && mypy

# Frontend (from repo root)
cd frontend && npm test && npm run typecheck && npm run build
```

All four commands should exit 0.

## Run the benchmark

```bash
cd backend && ./.venv/Scripts/python -m repopulse.scripts.benchmark \
  --scenarios-dir ../scenarios \
  --out ../docs/superpowers/plans/m6-evidence/benchmark.json
```

(On Linux/macOS replace `./.venv/Scripts/python` with `./.venv/bin/python`.)

The output should show `false_positive_rate: 0.0` and an MTTR
average around 5 s. See [docs/results-report.md](results-report.md) for
KPI definitions.

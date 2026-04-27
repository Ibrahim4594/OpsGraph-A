# Setup

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | 3.11+ | backend (FastAPI 0.136, pydantic 2.13) |
| Node.js | 20+ LTS | frontend (Next.js 15) |
| Docker | any current | OTel Collector (optional, only for telemetry validation runs) |
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
pytest                              # 209+ tests should pass
```

## Frontend

```bash
cd frontend
npm install
npm test                            # 53+ vitest specs
npm run build                       # production build (under 200 KB First Load JS)
```

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

```bash
./scripts/demo.sh
```

Boots backend + frontend + seeds canonical data, prints the URLs.
See [docs/demo/README.md](demo/README.md).

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

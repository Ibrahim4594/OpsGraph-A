#!/usr/bin/env bash
# Run ``alembic upgrade head`` against the dev compose Postgres.
#
# Resolution order for the DB URL:
#   1. ``$REPOPULSE_DATABASE_URL`` if already set in the environment.
#   2. The compose default — postgres on 127.0.0.1:55432, db ``repopulse``.
#
# Resolution order for the alembic runner:
#   1. Host venv (``backend/.venv``) — fastest dev loop.
#   2. Docker compose ``api`` service — works without a host venv.
#
# The script is idempotent: running it on an already-up-to-date DB exits
# 0 with no changes (alembic prints "Running upgrade ... -> head" only
# when there's something to do).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_URL="postgresql+psycopg://repopulse:repopulse@127.0.0.1:55432/repopulse"
DSN="${REPOPULSE_DATABASE_URL:-$DEFAULT_URL}"
export REPOPULSE_DATABASE_URL="$DSN"

echo "→ DSN: $DSN"

# Resolve runner.
if [[ -x "$ROOT/backend/.venv/Scripts/python" ]]; then
  PY="$ROOT/backend/.venv/Scripts/python"
elif [[ -x "$ROOT/backend/.venv/bin/python" ]]; then
  PY="$ROOT/backend/.venv/bin/python"
else
  PY=""
fi

if [[ -n "$PY" ]]; then
  echo "→ running alembic via host venv"
  cd "$ROOT/backend"
  "$PY" -m alembic upgrade head
elif command -v docker >/dev/null 2>&1; then
  echo "→ no host venv; running alembic via docker compose"
  docker compose -f "$ROOT/docker-compose.dev.yml" run --rm \
    -e REPOPULSE_DATABASE_URL="$DSN" \
    api alembic upgrade head
else
  echo "ERROR: no host venv (backend/.venv) and no docker available." >&2
  echo "  Run \`cd backend && python3 -m venv .venv && pip install -e '.[dev]'\` first," >&2
  echo "  or install Docker." >&2
  exit 1
fi

echo "→ migrations up to date."

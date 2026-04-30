#!/usr/bin/env bash
# Bring up the dev compose stack and run migrations.
#
# One command to: pull/build images, start postgres + api, wait for
# postgres health, run alembic upgrade head, print URLs. Re-running
# this on an already-up stack is safe — compose exits 0 immediately.
#
# Stop the stack with ``docker compose -f docker-compose.dev.yml down``
# (preserves the data volume) or ``... down -v`` (wipes Postgres data).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT/docker-compose.dev.yml"

if [[ -z "${REPOPULSE_API_SHARED_SECRET:-}" ]]; then
  echo "ERROR: REPOPULSE_API_SHARED_SECRET is not set." >&2
  echo "  export REPOPULSE_API_SHARED_SECRET=\"\$(openssl rand -hex 16)\"" >&2
  exit 1
fi
if [[ -z "${REPOPULSE_AGENTIC_SHARED_SECRET:-}" ]]; then
  echo "ERROR: REPOPULSE_AGENTIC_SHARED_SECRET is not set." >&2
  echo "  export REPOPULSE_AGENTIC_SHARED_SECRET=\"\$(openssl rand -hex 16)\"" >&2
  exit 1
fi

echo "→ docker compose up -d (postgres + api)"
docker compose -f "$COMPOSE_FILE" up -d

echo "→ waiting for postgres to report healthy"
# The api service depends_on postgres health, so by the time the api
# container reaches Running the DB is already accepting connections.
# We wait on the api container instead so the message lines up with
# what the developer experiences.
for _ in {1..30}; do
  status=$(docker compose -f "$COMPOSE_FILE" ps -q postgres \
    | xargs -I{} docker inspect -f '{{.State.Health.Status}}' {} 2>/dev/null || echo unknown)
  if [[ "$status" == "healthy" ]]; then
    break
  fi
  sleep 1
done
if [[ "$status" != "healthy" ]]; then
  echo "ERROR: postgres did not report healthy in 30s." >&2
  docker compose -f "$COMPOSE_FILE" logs postgres | tail -20
  exit 1
fi
echo "→ postgres healthy"

# The api container's entrypoint runs alembic on every restart; we run
# it once more from the host so the operator sees "Running upgrade" or
# a clean no-op explicitly.
"$ROOT/scripts/db-upgrade.sh"

cat <<EOF

╭─ RepoPulse dev stack up ────────────────────────────────╮
│                                                         │
│   API:        http://127.0.0.1:8000/healthz             │
│   Postgres:   127.0.0.1:55432 db=repopulse              │
│                                                         │
│   Stop (preserve data):                                 │
│     docker compose -f docker-compose.dev.yml down       │
│                                                         │
│   Stop AND wipe Postgres volume:                        │
│     docker compose -f docker-compose.dev.yml down -v    │
│                                                         │
╰─────────────────────────────────────────────────────────╯
EOF

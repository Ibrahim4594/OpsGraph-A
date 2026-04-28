#!/usr/bin/env bash
# RepoPulse demo runner.
#
# Boots backend (uvicorn) and frontend (next start), seeds the canonical
# demo dataset, and prints the URLs.
#
# Prerequisites — both must be set (no weak defaults):
#   export REPOPULSE_API_SHARED_SECRET="$(openssl rand -hex 16)"
#   export REPOPULSE_AGENTIC_SHARED_SECRET="$(openssl rand -hex 16)"
#
# Usage:
#   ./scripts/demo.sh                                # :8000 backend, :3000 frontend
#   PORT_BACKEND=8011 PORT_FRONTEND=3300 ./scripts/demo.sh
#
# Stops both servers on Ctrl-C.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT_BACKEND="${PORT_BACKEND:-8000}"
PORT_FRONTEND="${PORT_FRONTEND:-3000}"

if [[ -z "${REPOPULSE_API_SHARED_SECRET:-}" ]]; then
  echo "ERROR: REPOPULSE_API_SHARED_SECRET is not set." >&2
  echo "  export REPOPULSE_API_SHARED_SECRET=\"\$(openssl rand -hex 16)\"" >&2
  echo "The UI needs the same value as NEXT_PUBLIC_API_SHARED_SECRET (see below)." >&2
  exit 1
fi
if [[ -z "${REPOPULSE_AGENTIC_SHARED_SECRET:-}" ]]; then
  echo "ERROR: REPOPULSE_AGENTIC_SHARED_SECRET is not set." >&2
  echo "  export REPOPULSE_AGENTIC_SHARED_SECRET=\"\$(openssl rand -hex 16)\"" >&2
  exit 1
fi

CORS_ORIGINS="${REPOPULSE_CORS_ORIGINS:-http://127.0.0.1:${PORT_FRONTEND},http://localhost:${PORT_FRONTEND}}"

# Pick the python venv layout (Windows: Scripts, Unix: bin).
if [[ -x "$ROOT/backend/.venv/Scripts/python" ]]; then
  PY="$ROOT/backend/.venv/Scripts/python"
elif [[ -x "$ROOT/backend/.venv/bin/python" ]]; then
  PY="$ROOT/backend/.venv/bin/python"
else
  echo "ERROR: backend venv not found. Run \`cd backend && python3 -m venv .venv && pip install -e '.[dev]'\` first." >&2
  exit 1
fi

cleanup() {
  [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "${FRONTEND_PID:-}" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "→ booting backend on 127.0.0.1:$PORT_BACKEND"
(
  cd "$ROOT/backend"
  REPOPULSE_AGENTIC_ENABLED=true \
    REPOPULSE_AGENTIC_SHARED_SECRET="$REPOPULSE_AGENTIC_SHARED_SECRET" \
    REPOPULSE_API_SHARED_SECRET="$REPOPULSE_API_SHARED_SECRET" \
    REPOPULSE_CORS_ORIGINS="$CORS_ORIGINS" \
    "$PY" -m uvicorn repopulse.main:app --host 127.0.0.1 --port "$PORT_BACKEND" --log-level warning
) &
BACKEND_PID=$!
sleep 3

if [[ ! -f "$ROOT/frontend/.next/BUILD_ID" ]]; then
  echo "→ no frontend production build found; running 'npm run build' first"
  (cd "$ROOT/frontend" && npm run build)
fi

echo "→ booting frontend on :$PORT_FRONTEND"
(
  cd "$ROOT/frontend"
  NEXT_PUBLIC_BACKEND_URL="http://127.0.0.1:$PORT_BACKEND" \
    NEXT_PUBLIC_API_SHARED_SECRET="$REPOPULSE_API_SHARED_SECRET" \
    npm run start -- -p "$PORT_FRONTEND" -H 127.0.0.1
) &
FRONTEND_PID=$!
sleep 6

echo "→ seeding demo dataset"
REPOPULSE_AGENTIC_SHARED_SECRET="$REPOPULSE_AGENTIC_SHARED_SECRET" \
  "$PY" -m repopulse.scripts.seed_demo --url "http://127.0.0.1:$PORT_BACKEND" \
  --api-secret "$REPOPULSE_API_SHARED_SECRET" \
  || echo "WARN: seed failed (continuing)"

cat <<EOF

╭─ RepoPulse demo running ────────────────────────────────╮
│                                                         │
│   Dashboard:  http://127.0.0.1:$PORT_FRONTEND
│   API:        http://127.0.0.1:$PORT_BACKEND/healthz
│                                                         │
│   Pipeline API: Authorization Bearer (same as            │
│   REPOPULSE_API_SHARED_SECRET / NEXT_PUBLIC_*).        │
│   Bind: 127.0.0.1 only — do not expose raw to WAN.      │
│                                                         │
│   Press Ctrl-C to stop both servers.                    │
│                                                         │
╰─────────────────────────────────────────────────────────╯
EOF

wait

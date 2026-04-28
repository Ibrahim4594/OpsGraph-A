# Demo

## One command

Set secrets first (the script **fails fast** if they are unset):

```bash
export REPOPULSE_API_SHARED_SECRET="$(openssl rand -hex 16)"
export REPOPULSE_AGENTIC_SHARED_SECRET="$(openssl rand -hex 16)"
./scripts/demo.sh
```

Boots:
- backend (`uvicorn` on **127.0.0.1:8000** by default)
- frontend (`next start` on **127.0.0.1:3000** by default)
- seeds the canonical dataset (95 push events + 5 error-log events + 1 critical
  github event + 1 workflow-run usage event)

…and prints the URLs. Ctrl-C to stop.

If you want different ports:

```bash
PORT_BACKEND=8011 PORT_FRONTEND=3300 ./scripts/demo.sh
```

## What you should see

| Page | Screenshot | Expected state |
|---|---|---|
| **SLO board** (`/`) | ![slo](screenshots/slo.png) | Availability ~95% (red, over budget), Throughput counter, "slow burn" badge |
| **Incidents** (`/incidents`) | ![incidents](screenshots/incidents.png) | One critical incident + correlated event clusters, newest-first |
| **Recommendations** (`/recommendations`) | ![inbox](screenshots/recommendations.png) | One pending **escalate** (the critical event) + observed R1 fallbacks |
| **Action history** (`/actions`) | ![actions](screenshots/actions.png) | Auto-observe entries + workflow-run filter chip; approve/reject also recorded |
| Approve/reject toasts | ![toast](screenshots/toast.png) | Bottom-right Base UI toast with success/error tone |

## Architecture

See [architecture.md](architecture.md) for the system diagram and
[../architecture.md](../architecture.md) for the persistence/SLO context.

## Prereqs

See [../SETUP.md](../SETUP.md).

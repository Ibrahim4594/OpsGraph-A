# RepoPulse Operator Dashboard

Next.js 15 + Tailwind 4 frontend for the RepoPulse AIOps backend. Renders the SLO board, incidents timeline, recommendations inbox (with approval gate), and action history.

## Quick start

```bash
# install
npm install

# point at the backend (default: http://localhost:8000)
export NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:8000

# dev
npm run dev          # http://localhost:3000

# production
npm run build && npm run start
```

## Scripts

| Script | Purpose |
|---|---|
| `npm run dev` | Next.js dev server (App Router) |
| `npm run build` | Production build |
| `npm run start` | Serve the production build |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run lint` | `eslint` |
| `npm test` | `vitest run` (49 unit specs) |
| `npm run test:watch` | `vitest` watch mode |

## Pages

- `/` — SLO board (availability, error budget, throughput) with burn-rate badge
- `/incidents` — time-windowed incident timeline
- `/recommendations` — operator inbox with approve/reject + per-category runbook links
- `/actions` — chronological action history with kind filter (approve/reject/observe/workflow-run)

## Design system

The dashboard applies the typeui.sh `dashboard` skill — see [`docs/ui-design-system.md`](../docs/ui-design-system.md) for the token table, state matrix, accessibility requirements, and anti-patterns. Tokens live in [`src/app/globals.css`](src/app/globals.css) as semantic CSS custom properties.

## Security posture (M4)

**This dashboard ships without authentication.** The four GET endpoints and the two POST approval endpoints are unauthenticated by design — the operator UI is meant to run **local-only or behind a reverse proxy**. Do not expose port 3000 (or your reverse proxy's listening port) directly to the public internet.

The kill-switch indicator in the StatusBar reflects `REPOPULSE_AGENTIC_ENABLED` at the backend (read fresh per `/healthz` poll). Flipping the env var on the backend takes effect on the very next dashboard refresh — no UI button to toggle it.

SSO and per-operator session identity will land in a follow-up milestone; until then the `operator` field on approve/reject is free text recorded in the audit log, not authenticated.

## Architecture

- App Router with server components for data fetching (`getRecommendations`, `getIncidents`, `getActions`, `getSlo` in [`src/lib/api.ts`](src/lib/api.ts)).
- Client islands only where state is needed: `Sidebar` (active route), `ApprovalActions` (optimistic transition), `HistoryTable` (kind filter).
- Hand-written shadcn-style primitives under [`src/components/ui/`](src/components/ui/): `Card`, `Badge`, `Button`, `EmptyState`. No `npx shadcn add` runtime dependency.
- IBM Plex Sans loaded via `next/font/google`.

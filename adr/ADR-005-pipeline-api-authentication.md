# ADR-005 — Pipeline API shared-secret authentication

## Status

Accepted (v1.1.0)

## Context

The operator dashboard and automation scripts call the same FastAPI routes
that expose pipeline state (`GET` recommendations, incidents, actions, SLO)
and mutate approval state (`POST` approve/reject). Event ingest
(`POST /api/v1/events`) drives the orchestrator. Before v1.1 these routes were
unauthenticated, which is unsafe when the API is reachable beyond localhost.

JWT-based user sessions were deferred: the product ships as a **reference
demo** with a **single shared API key** per deployment, suitable for
closed networks and local development.

## Decision

1. **Pipeline API key** — All sensitive routes require
   `Authorization: Bearer <REPOPULSE_API_SHARED_SECRET>`.
2. **Fail closed** — If `REPOPULSE_API_SHARED_SECRET` is unset, protected
   routes return **503** (not 401), so operators misconfigure visibly instead
   of appearing “open”.
3. **Constant-time comparison** — The bearer token is verified with
   `hmac.compare_digest` (see `repopulse.api.pipeline_auth` and agentic routes
   in `repopulse.api.github_workflows`).
4. **Operator identity for approve/reject** — The audit `actor` is
   `Settings.api_operator_actor` (default `authenticated-api`). The request
   body must **not** carry a trusted operator name.
5. **Browser trust** — The Next.js app sends the pipeline secret via
   `NEXT_PUBLIC_API_SHARED_SECRET`, which is **exposed to anyone who can load
   the UI**. This is acceptable only for **demo / lab** deployments on
   `127.0.0.1`. Production should place the UI behind a reverse proxy that
   injects the secret server-side (BFF) or use end-user auth.

## Consequences

- `scripts/demo.sh` requires both `REPOPULSE_API_SHARED_SECRET` and
  `REPOPULSE_AGENTIC_SHARED_SECRET` and exports
  `NEXT_PUBLIC_API_SHARED_SECRET` for the UI.
- CI and pytest set `REPOPULSE_API_SHARED_SECRET` in `conftest.py`.
- **Separate** from GitHub agentic workflows, which use
  `REPOPULSE_AGENTIC_SHARED_SECRET` (CI maps `secrets.REPOPULSE_AGENTIC_TOKEN`
  into job env as `REPOPULSE_AGENTIC_TOKEN` for the caller script — same
  pattern: shared secret, not GitHub PAT on the backend).

## Alternatives considered

- **JWT sessions** — Better for multi-tenant production; higher implementation
  cost for this reference repo.
- **Next.js Route Handlers as sole BFF** — Would keep secrets off the client;
  chosen mitigation for v1.1 is **CORS allowlist + localhost bind** plus
  documentation; a full BFF migration is a follow-up.

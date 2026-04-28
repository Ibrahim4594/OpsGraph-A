# Security Model (v1.1)

## Trust boundaries

| Zone | Trust level | Notes |
|------|-------------|--------|
| **Demo / local** | Operator machine + `127.0.0.1` bind | `scripts/demo.sh` binds backend and frontend to loopback. **Do not** port-forward or expose these processes to untrusted networks without adding a reverse proxy and stronger auth. |
| **CI** | GitHub-hosted runners + repository secrets | Workflows inject secrets; minimal `permissions:` on workflow jobs (see each YAML). |
| **Production (if deployed)** | Your VPC / edge policy | Not prescribed here: use a BFF or OIDC, never rely on `NEXT_PUBLIC_*` secrets across the public internet. |

## Pipeline API (dashboard + ingest)

**Mechanism:** `Authorization: Bearer <REPOPULSE_API_SHARED_SECRET>`.

**Protected routes (non-exhaustive):**

- `POST /api/v1/events`
- `GET /api/v1/recommendations`, `GET /api/v1/incidents`, `GET /api/v1/actions`, `GET /api/v1/slo`
- `POST /api/v1/recommendations/{id}/approve`, `POST .../reject`

**Configuration (`backend/src/repopulse/config.py`):**

| Env var | Purpose |
|---------|---------|
| `REPOPULSE_API_SHARED_SECRET` | Shared bearer for pipeline routes. **Required** for normal operation; unset → **503** on protected routes. |
| `REPOPULSE_API_OPERATOR_ACTOR` | Audit field recorded on approve/reject (default `authenticated-api`). |
| `REPOPULSE_ALLOW_SIMULATE_ERROR` | When `true`, allows `simulate_error` on ingest (tests / load only). Default `false`. |
| `REPOPULSE_CORS_ORIGINS` | Comma-separated origins for `CORSMiddleware` (e.g. `http://127.0.0.1:3000`). Empty → no CORS (same-origin or reverse-proxy only). |

**Client:** The Next.js operator UI reads `NEXT_PUBLIC_API_SHARED_SECRET` and
sends the same bearer. This duplicates the secret in the browser bundle —
**demo-only**; see [ADR-005](../adr/ADR-005-pipeline-api-authentication.md).

**Approve / reject:** Identity is **not** taken from JSON body. The server
uses `api_operator_actor` only.

**Ingest limits:** Serialized `payload` JSON on `POST /api/v1/events` is
capped at **256 KiB** (validator in `repopulse.api.events`).

## GitHub agentic workflows (M5)

Unchanged at a high level: workflows use a **repository secret** bearer; the
backend stores `REPOPULSE_AGENTIC_SHARED_SECRET` and validates with
`hmac.compare_digest`. GitHub Actions jobs set `REPOPULSE_AGENTIC_TOKEN` from
`secrets.REPOPULSE_AGENTIC_TOKEN` for the Python caller — treat that value as
the same class of secret as `REPOPULSE_AGENTIC_SHARED_SECRET` on the server.

Kill switch, dry-run, scoped `permissions:`, and comment-only behavior remain
as documented in [ADR-003](../adr/ADR-003-agentic-execution-model.md) and
[agentic-workflows.md](agentic-workflows.md).

## Settings vs documentation

All **implemented** `REPOPULSE_*` keys for security-relevant behavior live in
`Settings` in `backend/src/repopulse/config.py`. Keys that are **not** in
`Settings` (for example a future `REPOPULSE_DATABASE_URL`) are **not**
documented here as active until code references them.

## Cross-origin browser access

When the UI origin differs from the API origin, set `REPOPULSE_CORS_ORIGINS`
to an explicit allowlist. The alternative pattern (Next Route Handlers as
BFF to avoid browser-held secrets) is described as a follow-up in ADR-005.

## Out of scope

End-user OIDC, per-operator RBAC, mTLS, and encryption-at-rest policy are
out of scope for this reference repository unless added in a later ADR.

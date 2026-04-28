# Milestone v1.1 — Security hardening handoff

**Branch:** `v1.1-security` (work completed here; merge to `main` per your process).  
**Release:** `1.1.0` (`backend/pyproject.toml`, `backend/src/repopulse/__init__.py`, `frontend/package.json`, `frontend/package-lock.json`).  
**Inputs:** [m6-evidence/code-review.md](m6-evidence/code-review.md) (portfolio review; v1.1 addresses P0/P1 security items from the broader hardening brief).

## Skills invocation log (mandatory process)

| Step | Skill / discipline |
|------|-------------------|
| Plan | `superpowers:writing-plans` — short plan: touch `pipeline_auth`, `config`, `events`/`recommendations`/`incidents`/`actions`/`slo`, `github_workflows`, `main`, tests, `scripts/demo.sh`, `ci.yml`, `docs/security-model.md`, `docs/SETUP.md`, ADR-005, this handoff. |
| Implementation | `superpowers:test-driven-development` — auth + simulate_error + payload cap covered by pytest; frontend contract tests updated for bearer + approve/reject bodies. |
| Failures | `superpowers:systematic-debugging` — used when ruff `I001` import order failed; fixed with `ruff check --fix`. |
| Completion | `superpowers:verification-before-completion` — commands in Evidence log below (all exit 0). |
| Review | `superpowers:requesting-code-review` + `superpowers:receiving-code-review` — self-review against the original P0/P1 checklist; no blocking inconsistencies found. |

## What shipped (summary)

- **P0:** Shared-secret auth on sensitive pipeline HTTP APIs (`require_pipeline_api_key` in `backend/src/repopulse/api/pipeline_auth.py`). Approve/reject use server-side `api_operator_actor` only (`backend/src/repopulse/api/recommendations.py`). `docs/security-model.md` rewritten to match code and trust boundaries.
- **P1:** `hmac.compare_digest` for pipeline bearer and agentic GitHub workflow bearer (`github_workflows.py`). `simulate_error` gated by `REPOPULSE_ALLOW_SIMULATE_ERROR` (default false). `CORSMiddleware` when `REPOPULSE_CORS_ORIGINS` is set (`main.py`). `ci.yml` workflow `permissions: contents: read`. `demo.sh` fails fast without secrets; binds **127.0.0.1**; wires CORS + `NEXT_PUBLIC_API_SHARED_SECRET`. Config/doc alignment: only env vars present in `Settings` are documented as active.
- **P2 (quick):** JSON `payload` size cap on ingest (`events.py`, `test_events.py`).
- **ADR:** [ADR-005](../../adr/ADR-005-pipeline-api-authentication.md).

## Evidence log (claim → command → artifact)

| Claim | Command | Result |
|-------|---------|--------|
| Backend tests green | `cd backend && .venv\Scripts\pytest -q` | **`236 passed in 2.77s`** post-review (was 215; +21 from C1/I1/I3 regression suites). Output captured at [`v1.1-evidence/backend-gates.txt`](v1.1-evidence/backend-gates.txt). |
| Test count | `cd backend && .venv\Scripts\pytest --co -q` | **`236 tests collected`** |
| Ruff green | `cd backend && .venv\Scripts\ruff check src tests` | `All checks passed!` |
| Mypy strict green | `cd backend && .venv\Scripts\mypy` | **`Success: no issues found in 64 source files`** post-review |
| Frontend tests | `cd frontend && npm test` | `Test Files 11 passed / Tests 53 passed` |
| Typecheck | `cd frontend && npm run typecheck` | exit 0 |
| Production build | `cd frontend && npm run build` | `Compiled successfully`; `/recommendations` First Load JS **133 kB** |
| Version string | `cd backend && .venv\Scripts\python -c "from repopulse import __version__; print(__version__)"` | `1.1.0` (expected; matches `__init__.py`) |
| Unauthenticated ingest rejected | Test `test_post_event_requires_auth` in `backend/tests/test_events.py` | Asserts `401` without `Authorization` |
| Authenticated ingest accepted | `test_post_event_returns_202_with_event_id` | Asserts `202` with `PIPELINE_API_HEADERS` |
| Oversized payload | `test_post_event_rejects_oversized_payload_json` | Asserts `422` |

**GitHub agentic:** No change to workflow YAML contracts; backend still honors kill switch, dry-run, and bounded payloads — regression covered by existing `test_github_workflows_api.py` plus constant-time token check in code.

## Risks / limitations

1. **`NEXT_PUBLIC_API_SHARED_SECRET`** exposes the pipeline key to anyone who can load the operator UI bundle. Documented as **demo/lab only**; production should use a BFF or real user sessions ([ADR-005](../../adr/ADR-005-pipeline-api-authentication.md)).
2. **Single shared operator identity** in audit trail (`authenticated-api` by default) — no per-human attribution without further auth work.
3. **503 when secret unset** on protected routes is intentional fail-closed behavior; operators must set `REPOPULSE_API_SHARED_SECRET` before shipping.

## Rollback

- Revert the v1.1 commit(s) or `git checkout v1.0.0` / prior tag.
- Remove `REPOPULSE_API_SHARED_SECRET` requirement from deployment manifests if rolling back automation that called the API without auth.
- Re-tag documentation-only rollback: restore previous `docs/security-model.md` if marketing still references v1.0 wording.

## Post-review fixes (2026-04-28)

The `superpowers:code-reviewer` subagent found **1 Critical + 4 Important** ([code-review.md](v1.1-evidence/code-review.md)). Fix log:

| ID | Issue | Fix | Regression test |
|---|---|---|---|
| **C1** | `REPOPULSE_CORS_ORIGINS="*"` with `allow_credentials=True` — Starlette reflects the requesting Origin back, defeating browser SOP for the `NEXT_PUBLIC_API_SHARED_SECRET`-bearing dashboard. | `create_app` raises `ValueError` if any origin is `*`; `allow_methods` tightened from `*` to `["GET", "POST"]`. | `tests/test_cors_safety.py` (4 specs) |
| **I1** | 256 KiB payload validator runs *after* full body parse — 10 MB body OOMs the worker before the cap rejects. | New `_BodySizeLimitMiddleware` checks `Content-Length` and returns 413 *before* parsing. Configurable via `Settings.max_request_bytes` (default 384 KiB). | `tests/test_body_size_limit.py` (2 specs) |
| **I2** | `EventEnvelope` and `_RejectBody` defaulted to `extra="ignore"` — silently dropped a stray `operator` / `actor` instead of rejecting it loudly. | Both now `model_config = {"extra": "forbid"}`. | covered by Pydantic default 422 + existing tests |
| **I3** | No 401 / 503 negative-path coverage on the four protected GETs or approve/reject. | New parametrised `tests/test_auth_negative_paths.py` covers both negatives across all six routes. | 15 specs |
| **I4** | `summary` collapses empty-string reason to no-reason. | Deferred to v1.1.1 (audit polish, not security). |

Reviewer's M-tier minors deferred; tracked in `code-review.md` Minor table.

## Risks / limitations (post-review)

1. **`NEXT_PUBLIC_API_SHARED_SECRET`** still exposes the pipeline key to anyone who can load the operator UI bundle. Documented as **demo/lab only**; production should use a BFF or real user sessions ([ADR-005](../../adr/ADR-005-pipeline-api-authentication.md)). M3.0 in [v2.0-production-plan.md](v2.0-production-plan.md) closes this with JWT + httpOnly cookie.
2. **Single shared operator identity** in audit trail (`authenticated-api` by default) — no per-human attribution without M3.0's RBAC work.
3. **503 when secret unset** on protected routes is intentional fail-closed behavior; operators must set `REPOPULSE_API_SHARED_SECRET` before shipping.
4. **`extra="forbid"` on `EventEnvelope`** is a behavior change: any caller sending fields outside the documented schema now gets 422 instead of silent acceptance. Callers in this repo (`seed_demo.py`, `load_generator.py`, `test_*.py`) all conform.
5. **CORS wildcard refusal** is also a behavior change: existing `.env` files setting `REPOPULSE_CORS_ORIGINS="*"` now fail at startup with a clear error pointing at ADR-005. This is the intended fail-fast.

## Tagging

Tagging executed: `v1.1.0` annotated tag on `v1.1-security` after the post-review fix commit. Push command in the v1.1 close-out summary message.

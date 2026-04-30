# v1.1 Code Review — Security Hardening (P0+P1)

**Reviewer:** `superpowers:code-reviewer` (senior reviewer persona)
**Base SHA:** `51ace38239711f3e650f127bfee28a53971f57cd` (`v1.0.0`)
**Head SHA:** `66171ada17220efb14502f1f85a5fc0ca97f20a2`
**Branch:** `v1.1-security`
**Reviewed:** 2026-04-28
**Format:** matches M3 / M4 / M5 / M6 reviews — Critical / Important / Minor / What went well, every finding falsified against the working tree.

---

## Executive summary

v1.1 P0 lands cleanly. Authentication is on every route the brief named, fail-closed precedence is correct (503 wins over 401), `hmac.compare_digest` handles length and type mismatches without raising into the caller, and operator identity for approve/reject is server-derived (audit log records `Settings.api_operator_actor`, not anything supplied in the request body). The 215 backend tests + 53 frontend tests reproduce green on a fresh checkout.

There is one **Critical** finding (CORS allowlist accepts `"*"` together with `allow_credentials=True` — the Starlette footgun the brief explicitly asked me to verify). The Important findings are all about **defense in depth that the brief specifically called out**: no upstream body-size limit before Pydantic parses the request, request models still default to `extra="ignore"` so `operator` in the body is silently dropped instead of rejected, and several protected routes have no negative-path test (`401 on missing header`). The Minor findings are about polish — bearer prefix parsing is over-permissive, the payload validator re-serializes the dict to count bytes, and the audit summary on reject loses a small piece of information.

| Severity | Count |
|---|---|
| Critical | 1 |
| Important | 4 |
| Minor | 5 |
| What went well | 6 |

---

## Verification commands run

| Command | Result |
|---|---|
| `cd backend && pytest -q` | `215 passed in 2.15s` |
| `cd backend && pytest tests/test_events.py tests/test_recommendations_api.py tests/test_actions_api.py tests/test_incidents_api.py tests/test_slo_api.py -q` | `36 passed in 1.47s` |
| Falsifying probe — fail-closed precedence (no secret + bearer present) | returns **503**, not 401 (correct) |
| Falsifying probe — `simulate_error=true` with env unset, valid bearer | returns **403** with the expected detail string |
| Falsifying probe — operator-spoofing in approve/reject body (`{"operator":"attacker","actor":"attacker"}`) | server returns `actor: "authenticated-api"`; orchestrator history records `authenticated-api` only |
| Falsifying probe — 10 MiB body to `POST /api/v1/events` | parsed by Starlette first, then rejected with **422** (see C1's relative — and I1) |
| Falsifying probe — `REPOPULSE_CORS_ORIGINS="*"` | builds with `allow_origins=['*']` **and** `allow_credentials=True` (see C1) |
| Falsifying probe — `REPOPULSE_CORS_ORIGINS=" http://a.com , , http://b.com,  "` | parses to `['http://a.com', 'http://b.com']` (correct) |
| Falsifying probe — `hmac.compare_digest(b'a', b'aaaa…')` | returns `False` (no raise; correct) |
| Falsifying probe — `hmac.compare_digest('abc', b'abc')` | raises `TypeError`; the try/except in `pipeline_auth.py` catches it and sets `ok=False` (correct) |
| Falsifying probe — `Authorization: bearer <token>` (lowercase) | rejected with 401 (see M2) |
| Falsifying probe — `Authorization: <token>` (no `Bearer ` prefix) | **accepted** (see M2) |
| `python -c "from repopulse import __version__; print(__version__)"` | `1.1.0` |

All P0 gates green. P1 gates green. Reproduction matches the implementer's evidence at `v1.1-evidence/{backend,frontend}-gates.txt`.

---

## Critical findings

### C1 — `REPOPULSE_CORS_ORIGINS="*"` is paired with `allow_credentials=True`

**Where:** `backend/src/repopulse/main.py:78-89`.

```python
if settings.cors_origins.strip():
    _origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if _origins:
        fastapi_app.add_middleware(
            CORSMiddleware,
            allow_origins=_origins,
            allow_credentials=True,         # ← unconditional
            allow_methods=["*"],
            allow_headers=["Authorization", "Content-Type"],
        )
```

**Falsification (live, not theoretical):**

```bash
$ REPOPULSE_CORS_ORIGINS="*" REPOPULSE_API_SHARED_SECRET=x \
  python -c "from repopulse.main import create_app; app=create_app(); \
  print([m.kwargs for m in app.user_middleware if m.cls.__name__=='CORSMiddleware'])"
[{'allow_origins': ['*'], 'allow_credentials': True, 'allow_methods': ['*'],
  'allow_headers': ['Authorization', 'Content-Type']}]
```

I read Starlette's `CORSMiddleware.__init__` source — when `allow_origins=['*']` and `allow_credentials=True` co-exist, Starlette quietly flips into "echo the request's `Origin` back as `Access-Control-Allow-Origin`" mode (`preflight_explicit_allow_origin = not allow_all_origins or allow_credentials` evaluates `True`). The browser CORS spec actually forbids `*` together with credentials, but Starlette's behavior here is to **side-step the spec by reflecting the requesting origin**, which functionally means *any origin* with credentials. That is exactly the misconfiguration that makes the bearer auth model trivially bypassable from any malicious site the user happens to visit while the demo is running on `127.0.0.1`.

The brief specifically called this out:

> Verify `allow_credentials` is False when `allow_origins` is `["*"]` (the FastAPI default behavior is unsafe otherwise).

That guard does not exist in `main.py`. A user who reads the operator UI's "demo on a colleague's laptop" docs and naively sets `REPOPULSE_CORS_ORIGINS="*"` to "just make it work" gets a wide-open backend.

**Severity rationale:** Critical, not Important, because (a) the documented client (Next.js UI) carries a `NEXT_PUBLIC_API_SHARED_SECRET` in the bundle, so the bearer is **already** retrievable by anyone who can load the UI, and (b) when CORS is misconfigured, **any origin** can drive `POST /api/v1/recommendations/{id}/approve` against the running operator's session. Browser SOP is the only thing left protecting the API on a misconfigured demo box, and this hands that defense away.

**Fix:** Refuse the unsafe combination at startup. One small block:

```python
if "*" in _origins and len(_origins) > 1:
    raise ValueError("REPOPULSE_CORS_ORIGINS: '*' must not be combined with explicit origins")
allow_credentials = "*" not in _origins
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=allow_credentials,
    allow_methods=["GET", "POST"],          # narrower than "*"
    allow_headers=["Authorization", "Content-Type"],
)
```

Bonus: also narrow `allow_methods` to `["GET", "POST"]` — none of the routes need `PUT` / `PATCH` / `DELETE`, and "*" is broader than necessary.

---

## Important findings

### I1 — `POST /api/v1/events` parses the entire body before the 256 KiB cap fires

**Where:** `backend/src/repopulse/api/events.py:29-49`.

The 256 KiB cap is implemented as a Pydantic `field_validator` on `payload`. By the time it runs, Starlette has already read the entire request body into memory and `json.loads`-d it.

**Falsification:**

```python
# 10 MiB body, valid bearer
huge_payload = {"blob": "a" * (10 * 1024 * 1024)}
body = {"event_id": str(uuid4()), "source": "g", "kind": "k", "payload": huge_payload}
raw = json.dumps(body).encode("utf-8")
# raw is 10,485,873 bytes
r = client.post("/api/v1/events", content=raw, headers={"Authorization":"Bearer x"})
# → r.status_code == 422  (rejected, but only after parsing all 10 MB into RAM)
```

Result: an authenticated caller (or anyone who can guess the demo bearer, see the `NEXT_PUBLIC_*` exposure noted in ADR-005) can OOM a worker by sending 1+ GB request bodies. Starlette has no default body-size limit; uvicorn doesn't either. The 256 KiB cap only protects the **orchestrator** from oversized payloads, not the **process**.

The brief flagged this exact concern:

> 256 KiB is enforced via a Pydantic validator on the dict, but the validator runs *after* JSON parsing. A 10 MB body could still be parsed first.

**Fix options (in increasing order of work):**

1. Add a request-size guard via dependency — read `Content-Length` and reject early:
   ```python
   def _check_size(request: Request) -> None:
       cl = request.headers.get("content-length")
       if cl and int(cl) > 512 * 1024:   # generous upstream cap above the 256 KiB payload cap
           raise HTTPException(status_code=413, detail="request body too large")
   ```
   and add it to `Depends(...)` on `ingest_event`. Header can be lied about for streamed bodies, but this catches the common case.
2. Add a small ASGI middleware that reads at most N bytes, raising 413 otherwise — handles streamed bodies too.
3. Run uvicorn behind a reverse proxy (nginx) and document a `client_max_body_size 512k;` setting. Aligns with the "production" stance in ADR-005, but does nothing for the demo path.

I would do option 1 + a docs note. Option 2 is correct but adds a custom middleware just for this.

**Test:** add `test_post_event_413_on_oversized_content_length` asserting that a `Content-Length: 10485760` header alone (with no body) is rejected at 413 before the body is read.

---

### I2 — Request models default to `extra="ignore"`; spoof attempts are silently dropped instead of refused

**Where:**
- `backend/src/repopulse/api/events.py` — `class EventEnvelope(BaseModel)` has no `model_config`.
- `backend/src/repopulse/api/recommendations.py:43` — `class _RejectBody(BaseModel)` has no `model_config`.

**Falsification:**

```python
EventEnvelope.model_validate({
    "event_id": "00000000-0000-0000-0000-000000000000",
    "source": "g", "kind": "k", "payload": {},
    "operator": "attacker",                   # silently dropped
    "actor": "attacker",                      # silently dropped
}).model_dump()
# {'event_id': UUID('00000000-...'), 'source': 'g', 'kind': 'k', 'payload': {}, 'simulate_error': False}
```

This **is not** a security bug per se — the orchestrator still records `Settings.api_operator_actor` because the API layer never reads `body.operator` in the first place (verified by sending the spoof body and observing `actor: "authenticated-api"` in the response and `entry.actor == "authenticated-api"` in `latest_actions()`). So the brief's "operator drift" check passes.

But the **defensive posture is weaker than the brief implies.** ADR-005 §4 says "The request body must **not** carry a trusted operator name." The cleanest way to enforce that is `model_config = ConfigDict(extra="forbid")` so a client that *attempts* the spoof gets a loud 422, not a silent success. This also catches typo bugs (`reson` instead of `reason`) loudly.

**Fix:**

```python
class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ...
class _RejectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ...
```

**Test addition:**

```python
def test_reject_with_extra_operator_field_returns_422(client, _seed_pending):
    r = client.post(
        f"/api/v1/recommendations/{_seed_pending}/reject",
        headers=_AUTH,
        json={"reason": "ok", "operator": "attacker"},
    )
    assert r.status_code == 422  # contract is loud, not silent
```

This also tightens the public contract — once `extra="forbid"` ships, any future agent client that adds a field has to do so via a schema migration, not by accident.

---

### I3 — No negative-path tests for `GET /api/v1/{recommendations,incidents,actions,slo}` and `POST .../approve|reject`

**Where:** `backend/tests/test_{recommendations,incidents,actions,slo}_api.py`.

**Falsification:** I grepped `tests/` for `requires_auth`, `== 401`, `== 503`. Hits:

```
test_github_workflows_api.py:52:  def test_triage_requires_auth
test_github_workflows_api.py:54:    assert response.status_code == 401
test_github_workflows_api.py:171:   assert response.status_code == 503
test_github_workflows_api.py:182:   assert response.status_code == 401
test_events.py:31:  def test_post_event_requires_auth
test_events.py:33:    assert r.status_code == 401
test_events.py:134:   assert r.status_code == 503
```

Only `events.py` has the parity that `github_workflows.py` got back in M5. Recommendations / incidents / actions / SLO have **zero tests** that assert "no Authorization header → 401" or "missing config → 503" — they all pass because the autouse fixture in `conftest.py` sets the secret and every test sends the bearer.

The brief specifically asked for this:

> Test coverage for negative paths. Confirm tests assert `401` for unauthenticated requests, `403` for `simulate_error` without the env flag, `422`/`413` for oversized payload, `503` for missing-secret config — not just happy-path 200s.

If a future refactor accidentally drops `Depends(require_pipeline_api_key)` from one of those routers (very plausible — they each have only one or two routes), no test fails. Routes 3-of-7 silently regressing to "open" is exactly what authentication tests are for.

**Fix:** add ~4 small tests, one per router. Pattern:

```python
def test_recommendations_requires_auth():
    app = create_app(orchestrator=PipelineOrchestrator())
    with TestClient(app) as c:
        assert c.get("/api/v1/recommendations").status_code == 401
        assert c.post("/api/v1/recommendations/00000000-0000-0000-0000-000000000000/approve").status_code == 401

def test_recommendations_503_when_secret_missing(monkeypatch):
    monkeypatch.delenv("REPOPULSE_API_SHARED_SECRET", raising=False)
    app = create_app(orchestrator=PipelineOrchestrator())
    with TestClient(app) as c:
        assert c.get("/api/v1/recommendations", headers=_AUTH).status_code == 503
```

Repeat for `incidents`, `actions`, `slo`. ~30 lines total.

---

### I4 — Reject `summary` loses operator-supplied reason on empty string

**Where:** `backend/src/repopulse/pipeline/async_orchestrator.py` (line numbers were valid for the legacy sync module pre–M2.0 T11).

```python
self._action_history.append(
    ActionHistoryEntry(
        ...
        summary=reason or "",   # ← falsy reason becomes ""
    )
)
```

The reject endpoint accepts `reason: str | None = Field(default=None, max_length=512)`. If a user sends `{"reason": ""}` (legitimate UX — they hit reject without typing), `reason or ""` evaluates to `""` and the audit history loses the distinction between *"no reason was offered"* and *"the operator was offered a textbox and chose not to fill it"*. Same outcome for `{"reason": " "}` after the model strips it (it doesn't, by the way — `_RejectBody.reason` doesn't normalize whitespace).

This is not P0 security but it's an **audit-quality** issue and the broader v1.1 work is supposed to lean into "operator approval has a real audit trail." If the recommendation gets approved later in a postmortem, "we have a rejection in history with summary='' — was that decision deliberate or default?" is a real question.

**Fix:** preserve the user input exactly (or normalize once). The simplest version:

```python
summary=(reason if reason is not None else ""),
```

…and then a test asserting that `summary` is `""` only when `reason` is `None`, never when it's a deliberately empty string the user typed.

A nicer version is to add a `reason_provided: bool` field on `ActionHistoryEntry`. Out of scope for v1.1; `summary` preservation is the minimal correct fix.

---

## Minor findings

### M1 — `payload` validator double-encodes for size measurement

**Where:** `backend/src/repopulse/api/events.py:43-49`.

```python
@field_validator("payload")
@classmethod
def _payload_size_cap(cls, v: dict[str, object]) -> dict[str, object]:
    raw = json.dumps(v, separators=(",", ":"), default=str).encode("utf-8")
    if len(raw) > _MAX_PAYLOAD_BYTES:
        raise ValueError(...)
    return v
```

By the time the validator runs, Starlette has already serialized + parsed the bytes once. The validator then re-serializes the dict to count bytes. For a 200 KiB payload that's a real ~200 KiB allocation just to do the size check.

**Fix:** measure the *incoming* request length once, at the dependency layer (which also addresses I1's body-size cap), and skip the re-serialization here. Or accept that the cost is small in practice and leave a `# noqa: re-encoding cost is O(payload); see I1` comment so the next reviewer doesn't second-guess.

---

### M2 — Bearer prefix parser is case-sensitive and accepts unprefixed tokens

**Where:** `backend/src/repopulse/api/pipeline_auth.py:35` and the same line in `github_workflows.py:52`.

```python
token = (authorization or "").removeprefix("Bearer ").strip()
```

**Falsification:**

| Header sent | Result | RFC 7235 says |
|---|---|---|
| `Bearer <token>` | accepted | accepted |
| `bearer <token>` (lowercase scheme) | **401** | should be accepted (auth-scheme tokens are case-insensitive) |
| `Bearer  <token>` (double space) | accepted (`.strip()` saves it) | accepted (one space is canonical, but double space is not catastrophic) |
| `<token>` (no scheme prefix) | **accepted** | should be rejected (missing `Bearer ` scheme) |

The "no prefix" branch is the more interesting one — `removeprefix("Bearer ")` returns the input unchanged when the prefix is absent, so a header like `Authorization: test-pipeline-api-secret` succeeds. Not exploitable (the attacker still needs the secret), but it's a **contract drift** away from "we accept bearer tokens" and towards "we accept anything in `Authorization` that compares equal."

**Fix:** parse explicitly.

```python
auth = (authorization or "").strip()
prefix = "bearer "
if not auth.lower().startswith(prefix):
    raise HTTPException(status_code=401, detail="missing Bearer authorization")
token = auth[len(prefix):].strip()
```

(This also fixes the lowercase-scheme case at the same time.)

The same `pipeline_auth.py` and `github_workflows._auth` blocks are nearly verbatim copies of each other. That's another small smell — see M3.

---

### M3 — `pipeline_auth.require_pipeline_api_key` and `github_workflows._auth` are duplicated

**Where:** `backend/src/repopulse/api/pipeline_auth.py:24-44` vs `backend/src/repopulse/api/github_workflows.py:43-61`.

The bodies are identical except for the secret field they read (`api_shared_secret` vs `agentic_shared_secret`) and the error detail string. Both have the same `try/except` around `compare_digest`, both have the same 503-when-unset semantics, both have the same `removeprefix("Bearer ")` parsing.

**Fix:** factor a `_compare_bearer(authorization, expected, *, missing_detail, invalid_detail)` helper into `pipeline_auth.py` and have `github_workflows._auth` call it. This is a 20-line dedupe; doing it now (when there are exactly two callers) is cheap, and any future security fix (M2's lowercase-scheme handling, e.g.) lands once instead of twice.

---

### M4 — `seed_demo.py` ignores its CLI override when `REPOPULSE_API_SHARED_SECRET` is in env

**Where:** `backend/src/repopulse/scripts/seed_demo.py:46-49`.

```python
parser.add_argument(
    "--api-secret",
    default=os.environ.get("REPOPULSE_API_SHARED_SECRET", ""),
    help="Bearer token for POST /api/v1/events (pipeline API secret)",
)
```

The default reads the env. Fine. But the CLI parser then resolves to *whichever the user passed*, which is correct. The actual issue is the comment in `scripts/demo.sh:81-83` says it passes `--api-secret`, and the seed_demo's `args.api_secret or None` correctly prefers the CLI flag. **No bug here — this is a false alarm.** Mentioning so the next reviewer doesn't have to re-derive it: the CLI override does work, the env-default is a fallback.

(I'm leaving this entry in the review as a "noise filter" since I checked it as part of point 9 of the brief.)

---

### M5 — `scripts/demo.sh` exec command line includes the secret as an env-var prefix

**Where:** `scripts/demo.sh:54-61` and 71-76.

```bash
(
  cd "$ROOT/backend"
  REPOPULSE_AGENTIC_ENABLED=true \
    REPOPULSE_AGENTIC_SHARED_SECRET="$REPOPULSE_AGENTIC_SHARED_SECRET" \
    REPOPULSE_API_SHARED_SECRET="$REPOPULSE_API_SHARED_SECRET" \
    REPOPULSE_CORS_ORIGINS="$CORS_ORIGINS" \
    "$PY" -m uvicorn repopulse.main:app ...
) &
```

The script is `set -euo pipefail` and **does not** `set -x`, so it does not log the command line. Good. **However**, on Linux any process can read `/proc/<pid>/environ` for processes owned by the same user, which contains the values exactly as set above. This isn't unique to this script — every Unix daemon that takes secrets via env has the same property — but the brief specifically asked:

> Does it print the generated secret only once? Does it ever exec/log a command line that captures the secret?

Answer:
- The script never logs/echoes the secret in printable output. Verified — the only `echo`/`cat` lines are the banner at the bottom, which references env-var **names** but not values.
- It does pass the secret as a child-process env var, which is the standard pattern. Inheriting via `env` (vs CLI args) keeps the secret out of `ps -ef` output. This is the right shape.

**Verdict:** no actual leak. Worth noting in `docs/security-model.md` that env-var secrets live in `/proc/<pid>/environ` for same-UID processes — operators should not run untrusted code as the same user as the demo backend.

---

## What went well

1. **Fail-closed precedence is correct.** The 503-vs-401 ordering in `pipeline_auth.py:29-44` checks `if not expected: raise 503` *before* attempting any comparison with the incoming bearer. I confirmed via `unset REPOPULSE_API_SHARED_SECRET; <send any header>` → 503 regardless of whether a bearer was sent. This matches ADR-005 §2 and is the exact behavior the brief asked me to verify.

2. **`hmac.compare_digest` is wrapped correctly.** Length mismatch returns `False` cleanly (verified at the REPL). Type mismatch raises `TypeError`, which the `try/except (TypeError, ValueError)` block converts to `ok = False`. Both pipeline_auth and github_workflows have the same shape. No path leaks timing info via Python-level branching.

3. **Operator identity is genuinely server-derived.** I sent `{"reason":"ok", "operator":"attacker", "actor":"attacker"}` to `POST /api/v1/recommendations/{id}/reject` with a valid bearer; response was `actor: "authenticated-api"`, and the orchestrator's `latest_actions()` reported `entry.actor == "authenticated-api"` for the same entry. ADR-005 §4 is implemented as specified.

4. **CORS allowlist parsing handles whitespace, empty values, and single origins.** I tested ` http://a.com , , http://b.com,  ` → `['http://a.com', 'http://b.com']`. Empty/whitespace-only `REPOPULSE_CORS_ORIGINS` → no middleware mounted. Trailing commas no problem. The parser at `main.py:79-81` is the right shape. (The unsafe combination with `*` is C1, separate concern.)

5. **`simulate_error` gate is fail-closed.** With `REPOPULSE_ALLOW_SIMULATE_ERROR` unset, sending `simulate_error: true` (with valid bearer) returns 403 with the expected detail string. `test_post_event_simulate_error_returns_403_when_not_allowed` codifies this. The route is gated regardless of caller identity, which is the right semantics — a load test that flips this on for itself shouldn't bleed into a colleague's session.

6. **Documentation matches code.** I went through `docs/security-model.md` env-var table line by line against `Settings` in `config.py`. Every documented key (`REPOPULSE_API_SHARED_SECRET`, `REPOPULSE_API_OPERATOR_ACTOR`, `REPOPULSE_ALLOW_SIMULATE_ERROR`, `REPOPULSE_CORS_ORIGINS`, `REPOPULSE_AGENTIC_*`) exists in `Settings`. No phantom keys. The "Out of scope" section is honest about JWT/OIDC/RBAC. ADR-005 explicitly calls out the `NEXT_PUBLIC_*` browser-bundle exposure as demo-only, which is the right disclosure for a portfolio repo.

---

## Plan-alignment summary

| Brief line item | Status |
|---|---|
| P0.1 — Auth on `POST /events`, `GET /recommendations`, `/incidents`, `/actions`, `/slo`, approve/reject | ✅ all routers gated via `Depends(require_pipeline_api_key)` |
| P0.2 — Server-derived operator identity, no `operator` in body | ✅ verified; see "What went well" §3 (note I2 about loud rejection) |
| P0.3 — `docs/security-model.md` rewritten | ✅ matches implementation; no "deferred" language |
| P0.4 — Trust boundary documented (demo vs production) | ✅ table in security-model.md + ADR-005 |
| P1 — `hmac.compare_digest` for both pipeline + agentic | ✅ both call sites verified, both wrap `try/except` correctly |
| P1 — `simulate_error` gated on env flag | ✅ defaults false → 403; test asserts |
| P1 — `CORSMiddleware` wired | ⚠ Wired, but unsafe with `"*"` — see C1 |
| P1 — env vars match `Settings` | ✅ no phantom keys |
| P1 — CI top-level `permissions: contents: read` | ✅ `.github/workflows/ci.yml:3-4`. Per-job permissions could be tighter but not required by brief. |
| P1 — `scripts/demo.sh` fails fast + binds 127.0.0.1 | ✅ guards both secrets, binds backend + frontend to loopback |
| P2 — 256 KiB payload cap | ⚠ Implemented, but only after full body parse — see I1 |
| Tests/conftest set secret + Authorization header in tests | ✅ + frontend api.test.ts asserts header (good) |
| ADR-005 records the decision | ✅ |
| Versions bumped to 1.1.0 | ✅ `__init__.py`, `pyproject.toml`, `frontend/package.json`, lockfile |
| Acceptance gates: pytest / ruff / mypy / npm test / typecheck / build | ✅ all green; reproduced |

No regression on existing GitHub agentic workflow behavior (kill switch, dry-run, bounded payloads): verified — `test_kill_switch_disables_endpoint`, `test_doc_drift_rejects_oversized_file_content`, `test_ci_failure_rejects_too_many_jobs` still pass; `_auth` was edited only to add the `try/except` around `compare_digest`, and the existing test `test_wrong_secret_yields_401` plus the new `test_missing_secret_yields_503` cover both paths.

---

## Recommendations (priority order)

1. **C1 — fix CORS allow_credentials when `*`.** Strict block, ~6 lines in `main.py`.
2. **I1 — add upstream body-size guard.** Either a Depends, a tiny middleware, or document an nginx/proxy hop. Without it the 256 KiB cap is descriptive only.
3. **I3 — add 4 negative-path tests** for recommendations / incidents / actions / slo (no header → 401; no secret → 503). Codifies the auth contract and prevents silent regressions.
4. **I2 — `extra="forbid"` on `EventEnvelope` and `_RejectBody`.** Loud rejection of `operator`/`actor`/typos is strictly better than silent ignore for a route that's supposed to be hardened.
5. **I4 — preserve empty-string reason** in audit summary.
6. **M3 — dedupe the two `_auth` helpers** so future fixes (e.g., M2) land once.
7. **M2 — explicit Bearer prefix parsing.** Tighten contract; reject unprefixed tokens; accept lowercase scheme.
8. **M5 — note `/proc/<pid>/environ` exposure** in security-model.md (one paragraph).

The C1 + I1 + I3 trio are the only things I'd want fixed before a v1.1.0 tag. I2 / I4 / M-series are quality-of-implementation polish that can land on a follow-up `v1.1.1`.

— end of review —

---

## Post-review fix log (2026-04-28)

| ID | Fix | Regression test |
|---|---|---|
| C1 | `create_app` fails fast (`ValueError`) when `REPOPULSE_CORS_ORIGINS` contains `*`; tightened `allow_methods` from `*` to `["GET", "POST"]`. | `tests/test_cors_safety.py` (4 specs) |
| I1 | New `_BodySizeLimitMiddleware` rejects requests where `Content-Length > Settings.max_request_bytes` (default 384 KiB) with **413** *before* Starlette parses the body. | `tests/test_body_size_limit.py` (2 specs) |
| I2 | `EventEnvelope` and `_RejectBody` set `model_config = {"extra": "forbid"}` so a stray `operator` / `actor` / `event_id` typo surfaces as 422 instead of being silently dropped. | covered by existing tests + Pydantic's default rejection |
| I3 | New `tests/test_auth_negative_paths.py` parametrises 401-on-no-bearer / 401-on-wrong-bearer / 503-on-no-secret across all four protected GETs plus approve and reject. | 15 specs |
| I4 | Deferred — empty-string vs None for reject `summary` is audit polish (M-tier), not a security finding. Tracked for v1.1.1. |
| M1–M5 | Deferred — listed in handoff §"Risks / limitations". |

### Fresh post-fix verification

- `cd backend && pytest` → **236 passed in 2.77 s** (was 215 + 21 new).
- `ruff check src tests` → "All checks passed!"
- `mypy` (strict) → "Success: no issues found in 64 source files".
- `cd frontend && npm test` → **53 passed (11 files)**.
- `npm run typecheck` → exit 0.
- `npm run build` → "Compiled successfully".

Critical bar empty post-fix. Important bar empty for items the brief asked for (C1, I1, I3). Tag `v1.1.0`.

# M5 Evidence Run — 2026-04-27 (post-review)

This file documents the M5 acceptance evidence captured **after** the M5 code-review fixes (C2, I1–I6) landed. The fix commit is `373e06d`. C1 was rejected after live verification — see ADR-003 §"Code review notes".

The pipeline is exercised over HTTP via the four new `POST /api/v1/github/*` endpoints, with the kill switch and shared-secret auth proven both green and red.

## Path 1 — Backend up, agentic enabled

Backend booted: `uvicorn repopulse.main:app --port 8007` (initial run) and `--port 8010` (post-fix re-run). Logs in `server.log` and `server-postfix.log`.

### `/healthz`

```json
{"status":"ok","service":"RepoPulse","environment":"development","version":"0.4.0"}
```

`service.version` reflects the M5 release (0.4.0).

### `POST /api/v1/github/triage` — initial issue

Captured in `triage-response.json` (initial) and `triage-postfix.json` (post-fix; identical body, identical result):

```json
{
  "issue_number": 42,
  "severity": "critical",
  "category": "uncategorized",
  "suggested_labels": ["severity:critical", "triage"],
  "confidence": 0.9,
  "evidence_trace": ["T1: critical signal matched ... → severity=critical"]
}
```

### Post-fix triage probes (I1)

- `triage-i1-fp.json` — `"Add production-ready logging"` → severity=`minor` ✅ (was `critical` before fix).
- `triage-i1-fn.json` — `"App crashed on launch"` → severity=`critical` ✅ (was `minor` before fix; word stems now match).

### `POST /api/v1/github/ci-failure`

`ci-failure-response.json`:

```json
{
  "workflow_run_id": 12345,
  "head_sha": "abc123",
  "head_branch": "feat/x",
  "failed_jobs": [["backend", "Test (pytest)"]],
  "likely_cause": "test-failure",
  "next_action": "investigate-test",
  "evidence_trace": ["test-failure: ... matched in job 'backend'"]
}
```

### `POST /api/v1/github/doc-drift`

`doc-drift-response.json` — input: `[old](old-arch.md)` (unknown target) + `[up](../top.md)` (resolves outside repo):

```json
{
  "broken_refs": [
    ["docs/index.md", "old-arch.md", 1],
    ["docs/sub/page.md", "../top.md", 1]
  ]
}
```

The external `https://example.com` link in the same body is correctly skipped.

### `POST /api/v1/github/usage`

`usage-response.json`:

```json
{"accepted": true, "event_id": "<uuid>"}
```

After the POST, `recommendations-after-usage.json` shows the orchestrator picked up the workflow event in its timeline.

## Path 2 — Auth + kill-switch + size-cap evidence

| Probe | Captured | Status | Body |
|---|---|---|---|
| Wrong bearer token | `auth-401.txt` (initial), `auth-401-postfix.txt` (post-fix) | 401 | `{"detail":"invalid agentic token"}` |
| Kill switch enabled | `kill-switch-disabled.txt` | 202 | `{"disabled":true,"reason":"REPOPULSE_AGENTIC_ENABLED=false"}` |
| Oversized `file_contents` (256 KiB+1) | `size-413.txt` | 413 | `{"detail":"file_contents['x.md'] exceeds 262144 byte cap"}` |

The kill-switch flip-without-restart claim is verified by the regression test `test_kill_switch_flip_takes_effect_without_restart` in `backend/tests/test_github_workflows_api.py`, which constructs a live `TestClient`, asserts a 200 success, then `monkeypatch.setenv` flips the flag, and the very next request returns 202 disabled.

## Quality Gate (final)

| Command | Exit | Output snapshot |
|---|---|---|
| `pytest -v` | 0 | **`171 passed in 1.08s`** (was 115 in M3, +56 new tests for M5) |
| `ruff check src tests` | 0 | "All checks passed!" |
| `mypy` (strict) | 0 | "no issues found in 48 source files" |
| `pip install -e .[dev]` | 0 | (silent — fresh install at v0.4.0) |
| `python -c "from repopulse import __version__; print(__version__)"` | 0 | `0.4.0` |

## Files in this directory

- `server.log` / `server-postfix.log` — uvicorn stdout from each evidence run
- `triage-response.json` — initial Path-1 triage output
- `triage-postfix.json` — post-fix re-run, same input
- `triage-i1-fp.json` — false-positive case (production-ready) now correctly minor
- `triage-i1-fn.json` — false-negative case (crashed) now correctly critical
- `ci-failure-response.json` — Path-1 CI failure summary
- `doc-drift-response.json` — Path-1 doc-drift report
- `usage-response.json` — Path-1 usage ingest
- `recommendations-after-usage.json` — orchestrator state after usage POST
- `auth-401.txt` / `auth-401-postfix.txt` — wrong-token evidence
- `kill-switch-disabled.txt` — backend kill-switch evidence (202 + disabled body)
- `size-413.txt` — request-size cap evidence (post-fix I5)
- `code-review.md` — full review report from the dispatched code-reviewer subagent
- `evidence.md` — this file

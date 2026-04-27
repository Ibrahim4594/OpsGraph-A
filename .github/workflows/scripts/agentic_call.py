"""Helper for agentic GitHub workflows.

Reads ``GITHUB_EVENT_PATH``, posts the relevant subset to the RepoPulse
backend's ``/api/v1/github/*`` endpoints, and writes the JSON response to
``$GITHUB_OUTPUT`` for the downstream comment-posting step. Standard library
only — no third-party HTTP client needed in the runner.

Subcommands:
    triage        — POST /api/v1/github/triage     (issues event)
    ci-failure    — POST /api/v1/github/ci-failure (workflow_run event)
    usage         — POST /api/v1/github/usage      (workflow_run telemetry)

Doc-drift uses a dedicated workflow that assembles its own request body —
not handled here.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def _backend_url() -> str:
    return os.environ["REPOPULSE_BACKEND_URL"].rstrip("/")


def _token() -> str:
    return os.environ["REPOPULSE_AGENTIC_TOKEN"]


def _post(path: str, body: dict[str, object]) -> dict[str, object]:
    request = urllib.request.Request(
        f"{_backend_url()}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_token()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _emit_output(name: str, value: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if not out:
        return
    with open(out, "a", encoding="utf-8") as fh:
        fh.write(f"{name}<<EOF\n{value}\nEOF\n")


def _load_event() -> dict[str, object]:
    path = os.environ["GITHUB_EVENT_PATH"]
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _usage_body(event: dict[str, object]) -> dict[str, object]:
    run = event.get("workflow_run") or {}
    started = run.get("run_started_at") or run.get("created_at")
    completed = run.get("updated_at")
    duration = 0.0
    if started and completed:
        from datetime import datetime
        try:
            duration = (
                datetime.fromisoformat(str(completed).replace("Z", "+00:00"))
                - datetime.fromisoformat(str(started).replace("Z", "+00:00"))
            ).total_seconds()
        except ValueError:
            duration = 0.0
    repo = event.get("repository") or {}
    return {
        "workflow_name": str(run.get("name", "unknown")),
        "run_id": int(run.get("id", 0)),
        "duration_seconds": float(duration),
        "conclusion": str(run.get("conclusion", "neutral")),
        "repository": str(repo.get("full_name", "")),
        "runner": "linux",
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: agentic_call.py <triage|ci-failure|usage>", file=sys.stderr)
        return 2
    cmd = sys.argv[1]
    event = _load_event()

    try:
        if cmd == "triage":
            result = _post("/api/v1/github/triage", event)
        elif cmd == "ci-failure":
            result = _post(
                "/api/v1/github/ci-failure",
                {"payload": event, "failed_jobs": []},
            )
        elif cmd == "usage":
            result = _post("/api/v1/github/usage", _usage_body(event))
        else:
            print(f"unknown subcommand: {cmd}", file=sys.stderr)
            return 2
    except urllib.error.HTTPError as exc:
        print(f"backend HTTP error: {exc.code} {exc.reason}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"backend unreachable: {exc.reason}", file=sys.stderr)
        return 1

    serialized = json.dumps(result)
    _emit_output("result_json", serialized)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

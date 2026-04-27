"""Seed the running backend with the canonical demo dataset.

Usage:
    python -m repopulse.scripts.seed_demo --url http://127.0.0.1:8000

100 push events + 5 error events + 1 critical github event + (optionally)
1 workflow-run usage event when REPOPULSE_AGENTIC_SHARED_SECRET is set.
Idempotent against a fresh backend; safe to re-run because the M3 dedup
layer handles repeated incident content signatures.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
import uuid


def _post(
    base_url: str, path: str, body: dict[str, object], *, secret: str | None = None
) -> None:
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5):
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--secret",
        default=os.environ.get("REPOPULSE_AGENTIC_SHARED_SECRET", ""),
    )
    args = parser.parse_args()
    base = args.url.rstrip("/")

    for i in range(95):
        _post(base, "/api/v1/events", {
            "event_id": str(uuid.uuid4()),
            "source": "github", "kind": "push",
            "payload": {"sha": f"abc{i}"},
        })
    for i in range(5):
        _post(base, "/api/v1/events", {
            "event_id": str(uuid.uuid4()),
            "source": "otel-logs", "kind": "error-log",
            "payload": {"severity": "error", "message": f"err {i}"},
        })
    _post(base, "/api/v1/events", {
        "event_id": str(uuid.uuid4()),
        "source": "github", "kind": "incident",
        "payload": {"severity": "critical", "message": "demo outage"},
    })
    if args.secret:
        try:
            _post(base, "/api/v1/github/usage", {
                "workflow_name": "agentic-issue-triage",
                "run_id": 12345, "duration_seconds": 18.4,
                "conclusion": "success",
                "repository": "Ibrahim4594/OpsGraph-A",
                "runner": "linux",
            }, secret=args.secret)
        except urllib.error.HTTPError as exc:
            print(
                f"WARN: workflow-run seed skipped — backend returned "
                f"HTTP {exc.code}. Set REPOPULSE_AGENTIC_SHARED_SECRET on "
                f"both sides if you want this seeded."
            )

    print(f"demo dataset seeded against {base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

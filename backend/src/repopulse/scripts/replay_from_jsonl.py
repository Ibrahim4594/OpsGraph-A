"""Replay an ingest log from JSONL into the persistent orchestrator.

M2.0 task 8. Used by operators to rebuild the database state from a
captured event stream — for example, restoring a non-prod environment
from a prod ingest dump, or back-filling a fresh DB after a 0001
downgrade-and-reupgrade cycle.

CLI
---

::

    python -m repopulse.scripts.replay_from_jsonl path/to/events.jsonl
    python -m repopulse.scripts.replay_from_jsonl path/to/events.jsonl --skip-invalid
    python -m repopulse.scripts.replay_from_jsonl - --skip-invalid     # stdin

Input contract
--------------

One JSON object per line (JSONL / NDJSON). Each object must satisfy the
:class:`repopulse.api.events.EventEnvelope` schema:

::

    {"event_id": "<uuid>", "source": "github", "kind": "push", "payload": {...}}

Empty lines and lines containing only whitespace are silently ignored.

Strict (default) vs ``--skip-invalid``
--------------------------------------

The default is **strict**: the first malformed line, validation error,
or ingest failure aborts the run with a :class:`ReplayError` that names
the line number. This is what the operator wants for a clean re-run
where the JSONL is supposed to be trustworthy.

``--skip-invalid`` switches to tolerant mode: invalid lines are counted
in ``stats.invalid`` and skipped. Use this for forensic replays of
known-dirty logs.

Idempotency
-----------

The orchestrator's ``ingest`` is idempotent on ``event_id`` (same
contract as ``POST /api/v1/events`` — see ``docs/ingest-idempotency.md``).
Replaying the same JSONL twice is safe: the second run reports every
event as a duplicate, no rows are duplicated, no recommendations are
re-emitted.

The replay is **ingest-only**: it does not call ``orchestrator.evaluate()``.
After the replay finishes, the operator typically POSTs an empty
``/api/v1/events`` cycle (or invokes evaluate via a forthcoming
admin endpoint) so the recommendations + action_history rows are
re-derived from the replayed events.

Stats output
------------

At end of run we print the :class:`ReplayStats` summary:

::

    Replay complete: total=42 accepted=39 duplicates=2 invalid=1 failed=0

with a non-zero exit code when ``failed > 0`` or when strict mode
aborts.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from pydantic import ValidationError

from repopulse.api.events import EventEnvelope
from repopulse.config import Settings
from repopulse.db.engine import make_engine_from_settings, make_session_factory
from repopulse.pipeline.async_orchestrator import PipelineOrchestrator


@dataclass
class ReplayStats:
    """Counters reported at end of run.

    - ``total_lines`` — non-blank lines fed into the parser. Blank lines
      are not counted (they're a JSONL formatting convention, not data).
    - ``accepted`` — fresh ingests (orchestrator returned a NormalizedEvent).
    - ``duplicates`` — orchestrator returned ``None`` because the
      ``event_id`` was already in ``raw_events``.
    - ``invalid`` — JSON parse errors + EventEnvelope validation errors.
      Only meaningful in ``skip_invalid`` mode; in strict mode the run
      aborts on the first invalid line.
    - ``failed`` — orchestrator-level errors (DB connectivity, etc.).
      Same strict / tolerant split as ``invalid``.
    """

    total_lines: int = 0
    accepted: int = 0
    duplicates: int = 0
    invalid: int = 0
    failed: int = 0


class ReplayError(RuntimeError):
    """Raised in strict mode on the first invalid line or ingest failure.

    The message always carries the 1-based line number so the operator
    can ``sed -n '<lineno>p' file.jsonl`` to inspect.
    """


async def replay_stream(
    stream: Iterable[str],
    orchestrator: PipelineOrchestrator,
    *,
    skip_invalid: bool = False,
) -> ReplayStats:
    """Iterate ``stream`` line-by-line, ingesting each as an EventEnvelope.

    The stream is anything yielding ``str`` per iteration — a file
    handle (``open(path, "r")``), an :class:`io.StringIO`, or a list
    of strings. Lines may include a trailing newline; we strip them.
    """
    stats = ReplayStats()
    for lineno, raw in enumerate(stream, start=1):
        line = raw.strip()
        if not line:
            continue
        stats.total_lines += 1

        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            stats.invalid += 1
            if skip_invalid:
                continue
            raise ReplayError(
                f"line {lineno}: invalid JSON ({exc.msg})"
            ) from exc

        try:
            envelope = EventEnvelope.model_validate(obj)
        except ValidationError as exc:
            stats.invalid += 1
            if skip_invalid:
                continue
            raise ReplayError(
                f"line {lineno}: invalid envelope "
                f"({exc.error_count()} validation error(s))"
            ) from exc

        try:
            normalized = await orchestrator.ingest(envelope)
        except Exception as exc:
            stats.failed += 1
            if skip_invalid:
                continue
            raise ReplayError(
                f"line {lineno}: ingest failed ({type(exc).__name__}: {exc})"
            ) from exc

        if normalized is None:
            stats.duplicates += 1
        else:
            stats.accepted += 1

    return stats


def _open_input(path: str) -> Iterator[str]:
    """Yield lines from ``path`` (or stdin if ``path == '-'``)."""
    if path == "-":
        yield from sys.stdin
        return
    with Path(path).open("r", encoding="utf-8") as f:
        yield from f


async def _build_orchestrator() -> tuple[PipelineOrchestrator, object]:
    """Wire a real DB-backed orchestrator from environment settings.

    Returns ``(orchestrator, engine)`` so the caller can dispose the
    engine after the replay finishes.
    """
    settings = Settings()
    if not settings.database_url:
        raise RuntimeError(
            "REPOPULSE_DATABASE_URL is unset; replay needs a configured "
            "DB. Set the env var to point at the same Postgres instance "
            "the orchestrator writes to in production."
        )
    engine = make_engine_from_settings(settings)
    session_maker = make_session_factory(engine)
    return PipelineOrchestrator(session_maker=session_maker), engine


async def _async_main(args: argparse.Namespace) -> int:
    orchestrator, engine = await _build_orchestrator()
    try:
        stats = await replay_stream(
            _open_input(args.path),
            orchestrator,
            skip_invalid=args.skip_invalid,
        )
    finally:
        # AsyncEngine.dispose() is async; the engine type is stripped
        # here to keep the helper untyped from main.py's perspective.
        await engine.dispose()  # type: ignore[attr-defined]
    sys.stdout.write(format_stats(stats) + "\n")
    return 0 if stats.failed == 0 else 1


def format_stats(stats: ReplayStats) -> str:
    return (
        "Replay complete: "
        f"total={stats.total_lines} "
        f"accepted={stats.accepted} "
        f"duplicates={stats.duplicates} "
        f"invalid={stats.invalid} "
        f"failed={stats.failed}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m repopulse.scripts.replay_from_jsonl",
        description="Replay a JSONL ingest log into the orchestrator.",
    )
    parser.add_argument(
        "path",
        type=str,
        help="Path to the JSONL file. Use '-' to read from stdin.",
    )
    parser.add_argument(
        "--skip-invalid",
        action="store_true",
        help=(
            "Tolerant mode: count invalid lines in stats.invalid and "
            "continue, instead of aborting on the first error. Default "
            "is strict (fail fast with the line number)."
        ),
    )
    args = parser.parse_args(argv)
    try:
        return asyncio.run(_async_main(args))
    except ReplayError as exc:
        sys.stderr.write(f"replay aborted: {exc}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())


# Re-export the ``IO`` import only to keep import-time symbols cohesive
# for unit-test introspection; not part of the public API.
_ = IO  # type: ignore[unused-ignore]

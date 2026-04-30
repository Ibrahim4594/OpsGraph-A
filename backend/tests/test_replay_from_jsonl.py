"""Unit tests for :mod:`repopulse.scripts.replay_from_jsonl` (M2.0 task 8).

Strict scope: parsing, validation, idempotency, and stat-counter
correctness. Drives the in-memory async orchestrator helper from T6 —
no real DB, no Docker.
"""
from __future__ import annotations

import io
import json
from uuid import uuid4

import pytest

from repopulse.scripts.replay_from_jsonl import (
    ReplayError,
    ReplayStats,
    format_stats,
    replay_stream,
)
from tests._inmem_orchestrator import make_inmem_orchestrator


def _envelope_dict() -> dict[str, object]:
    return {
        "event_id": str(uuid4()),
        "source": "github",
        "kind": "push",
        "payload": {"ref": "refs/heads/main"},
    }


def _line(envelope: dict[str, object]) -> str:
    return json.dumps(envelope) + "\n"


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


async def test_replay_happy_path_ingests_every_envelope() -> None:
    orch, state = make_inmem_orchestrator()
    e1 = _envelope_dict()
    e2 = _envelope_dict()
    stream = io.StringIO(_line(e1) + _line(e2))

    stats = await replay_stream(stream, orch)

    assert stats.total_lines == 2
    assert stats.accepted == 2
    assert stats.duplicates == 0
    assert stats.invalid == 0
    assert stats.failed == 0
    assert len(state.raw_events) == 2
    assert len(state.normalized_events) == 2


async def test_replay_skips_blank_and_whitespace_only_lines() -> None:
    orch, _state = make_inmem_orchestrator()
    e1 = _envelope_dict()
    stream = io.StringIO("\n   \n" + _line(e1) + "\n\n")

    stats = await replay_stream(stream, orch)

    assert stats.total_lines == 1
    assert stats.accepted == 1


# ---------------------------------------------------------------------------
# duplicates (idempotency)
# ---------------------------------------------------------------------------


async def test_replay_duplicates_count_separately_from_accepted() -> None:
    """Replaying the same envelope twice produces one ``accepted`` and
    one ``duplicates`` — orchestrator state must show only one row."""
    orch, state = make_inmem_orchestrator()
    e1 = _envelope_dict()
    stream = io.StringIO(_line(e1) + _line(e1))

    stats = await replay_stream(stream, orch)

    assert stats.total_lines == 2
    assert stats.accepted == 1
    assert stats.duplicates == 1
    assert len(state.raw_events) == 1
    assert len(state.normalized_events) == 1


async def test_full_replay_is_idempotent_when_run_twice() -> None:
    """Operator runs ``replay_from_jsonl`` against the same file twice —
    first run accepts everything, second run reports every event as a
    duplicate and writes nothing new."""
    orch, state = make_inmem_orchestrator()
    envs = [_envelope_dict() for _ in range(3)]
    payload = "".join(_line(e) for e in envs)

    first = await replay_stream(io.StringIO(payload), orch)
    second = await replay_stream(io.StringIO(payload), orch)

    assert first.accepted == 3
    assert first.duplicates == 0
    assert second.accepted == 0
    assert second.duplicates == 3
    assert len(state.raw_events) == 3


# ---------------------------------------------------------------------------
# malformed JSON
# ---------------------------------------------------------------------------


async def test_replay_strict_mode_aborts_on_malformed_json_with_line_number() -> None:
    orch, _state = make_inmem_orchestrator()
    e1 = _envelope_dict()
    # Line 2 is malformed.
    stream = io.StringIO(_line(e1) + "{not valid json\n")

    with pytest.raises(ReplayError, match=r"line 2.*invalid JSON"):
        await replay_stream(stream, orch)


async def test_replay_skip_invalid_mode_counts_malformed_json() -> None:
    orch, state = make_inmem_orchestrator()
    e1 = _envelope_dict()
    stream = io.StringIO(
        "not-json\n" + _line(e1) + "{still bad\n"
    )

    stats = await replay_stream(stream, orch, skip_invalid=True)

    assert stats.total_lines == 3
    assert stats.accepted == 1
    assert stats.invalid == 2
    assert stats.duplicates == 0
    assert stats.failed == 0
    assert len(state.raw_events) == 1


# ---------------------------------------------------------------------------
# validation (missing required fields)
# ---------------------------------------------------------------------------


async def test_replay_strict_mode_aborts_on_missing_event_id() -> None:
    orch, _state = make_inmem_orchestrator()
    bad = _envelope_dict()
    del bad["event_id"]
    stream = io.StringIO(_line(bad))

    with pytest.raises(ReplayError, match=r"line 1.*invalid envelope"):
        await replay_stream(stream, orch)


async def test_replay_strict_mode_aborts_on_invalid_uuid() -> None:
    orch, _state = make_inmem_orchestrator()
    bad = _envelope_dict()
    bad["event_id"] = "not-a-uuid"
    stream = io.StringIO(_line(bad))

    with pytest.raises(ReplayError, match=r"line 1.*invalid envelope"):
        await replay_stream(stream, orch)


async def test_replay_skip_invalid_collects_validation_errors() -> None:
    orch, state = make_inmem_orchestrator()
    missing_event_id = _envelope_dict()
    del missing_event_id["event_id"]
    bad_uuid = _envelope_dict()
    bad_uuid["event_id"] = "not-a-uuid"
    missing_source = _envelope_dict()
    del missing_source["source"]
    good = _envelope_dict()

    stream = io.StringIO(
        _line(missing_event_id)
        + _line(bad_uuid)
        + _line(missing_source)
        + _line(good)
    )

    stats = await replay_stream(stream, orch, skip_invalid=True)

    assert stats.total_lines == 4
    assert stats.accepted == 1
    assert stats.invalid == 3
    assert len(state.raw_events) == 1


# ---------------------------------------------------------------------------
# stats formatting (operational output)
# ---------------------------------------------------------------------------


def test_format_stats_renders_one_line_summary() -> None:
    out = format_stats(
        ReplayStats(
            total_lines=42,
            accepted=39,
            duplicates=2,
            invalid=1,
            failed=0,
        )
    )
    assert (
        out
        == "Replay complete: total=42 accepted=39 duplicates=2 invalid=1 failed=0"
    )

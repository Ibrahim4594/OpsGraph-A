"""Repository protocol marker + shared helpers.

The protocol is intentionally empty — concrete repos define their own
operations because aggregates differ. The marker exists so static analysis
can spot a "repo-shaped" thing in DI wiring (T5 orchestrator facade).

The :func:`utc_now` helper centralises ``datetime.now(tz=UTC)`` so test
fakes can be injected per-repo at the orchestrator level without each
repo importing ``datetime`` directly.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession


@runtime_checkable
class Repository(Protocol):
    """Marker protocol — every repo takes an ``AsyncSession`` at construction."""

    def __init__(self, session: AsyncSession) -> None: ...


def utc_now() -> datetime:
    return datetime.now(tz=UTC)

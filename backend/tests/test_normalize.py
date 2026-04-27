"""Normalization pipeline contract."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from repopulse.api.events import EventEnvelope
from repopulse.pipeline.normalize import NormalizedEvent, normalize

_RECEIVED = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


def _envelope(**overrides: object) -> EventEnvelope:
    base: dict[str, object] = {
        "event_id": uuid4(),
        "source": "github",
        "kind": "push",
        "payload": {},
    }
    base.update(overrides)
    return EventEnvelope.model_validate(base)


def test_normalize_preserves_event_id_and_received_at() -> None:
    env = _envelope()
    n = normalize(env, received_at=_RECEIVED)
    assert n.event_id == env.event_id
    assert n.received_at == _RECEIVED


def test_normalize_falls_back_to_received_at_when_no_occurred_at() -> None:
    n = normalize(_envelope(), received_at=_RECEIVED)
    assert n.occurred_at == _RECEIVED


def test_normalize_parses_occurred_at_from_payload() -> None:
    env = _envelope(payload={"occurred_at": "2026-04-26T08:30:00+00:00"})
    n = normalize(env, received_at=_RECEIVED)
    assert n.occurred_at == datetime(2026, 4, 26, 8, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    ("source", "kind", "expected_kind"),
    [
        ("github", "push", "push"),
        ("github", "pull_request", "pull_request"),
        ("otel-metrics", "anything", "metric-spike"),
        ("otel-logs", "anything", "info-log"),
        ("custom-source", "weird-kind", "unknown-weird-kind"),
    ],
)
def test_normalize_kind_taxonomy(source: str, kind: str, expected_kind: str) -> None:
    n = normalize(_envelope(source=source, kind=kind), received_at=_RECEIVED)
    assert n.kind == expected_kind


def test_normalize_otel_log_with_error_severity_becomes_error_log() -> None:
    env = _envelope(source="otel-logs", kind="anything", payload={"severity": "error"})
    n = normalize(env, received_at=_RECEIVED)
    assert n.kind == "error-log"
    assert n.severity == "error"


def test_normalize_severity_explicit_overrides_inferred() -> None:
    env = _envelope(payload={"severity": "critical"})
    assert normalize(env, received_at=_RECEIVED).severity == "critical"


def test_normalize_severity_inference_for_ci_failure() -> None:
    env = _envelope(kind="ci-failure")
    assert normalize(env, received_at=_RECEIVED).severity == "error"


def test_normalize_severity_inference_default_info() -> None:
    assert normalize(_envelope(), received_at=_RECEIVED).severity == "info"


def test_normalize_attributes_flattened_to_strings() -> None:
    env = _envelope(payload={"count": 3, "ref": "refs/heads/main", "nested": {"a": 1}})
    n = normalize(env, received_at=_RECEIVED)
    assert n.attributes["count"] == "3"
    assert n.attributes["ref"] == "refs/heads/main"
    assert n.attributes["nested"] == '{"a": 1}'


def test_normalize_returns_frozen_dataclass() -> None:
    from dataclasses import FrozenInstanceError

    n = normalize(_envelope(), received_at=_RECEIVED)
    assert isinstance(n, NormalizedEvent)
    with pytest.raises(FrozenInstanceError):
        n.kind = "mutated"  # type: ignore[misc]

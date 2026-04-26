"""Synthetic load generator contract."""
from collections.abc import Callable

import pytest

from repopulse.scripts.load_generator import LoadResult, generate_load


def _make_fake_post(error_status: int = 500, success_status: int = 202) -> Callable[
    [str, dict[str, object]], int
]:
    """Return a fake post callable. Status is decided by simulate_error in the envelope."""

    def fake_post(url: str, envelope: dict[str, object]) -> int:
        if envelope.get("simulate_error"):
            return error_status
        return success_status

    return fake_post


def test_generate_load_total_matches_requests() -> None:
    result = generate_load(
        requests=10,
        error_rate=0.0,
        target_url="http://test/api/v1/events",
        post=_make_fake_post(),
    )
    assert result.total == 10


def test_generate_load_zero_error_rate_all_succeed() -> None:
    result = generate_load(
        requests=20,
        error_rate=0.0,
        target_url="http://test/api/v1/events",
        post=_make_fake_post(),
    )
    assert result.success_count == 20
    assert result.error_count == 0


def test_generate_load_full_error_rate_all_fail() -> None:
    result = generate_load(
        requests=10,
        error_rate=1.0,
        target_url="http://test/api/v1/events",
        post=_make_fake_post(),
    )
    assert result.error_count == 10
    assert result.success_count == 0


def test_generate_load_error_rate_proportional() -> None:
    result = generate_load(
        requests=100,
        error_rate=0.2,
        target_url="http://test/api/v1/events",
        post=_make_fake_post(),
    )
    # 20% of 100 = 20 errors expected (deterministic, not random)
    assert result.error_count == 20
    assert result.success_count == 80


def test_generate_load_records_one_latency_per_request() -> None:
    result = generate_load(
        requests=5,
        error_rate=0.4,
        target_url="http://test/api/v1/events",
        post=_make_fake_post(),
    )
    assert len(result.latencies_ms) == 5
    assert all(latency >= 0.0 for latency in result.latencies_ms)


def test_generate_load_calls_post_with_target_url() -> None:
    seen_urls: list[str] = []

    def recording_post(url: str, _envelope: dict[str, object]) -> int:
        seen_urls.append(url)
        return 202

    generate_load(
        requests=3,
        error_rate=0.0,
        target_url="http://app:8000/api/v1/events",
        post=recording_post,
    )
    assert seen_urls == ["http://app:8000/api/v1/events"] * 3


def test_generate_load_envelope_has_required_fields() -> None:
    seen: list[dict[str, object]] = []

    def recording_post(_url: str, envelope: dict[str, object]) -> int:
        seen.append(envelope)
        return 202

    generate_load(
        requests=2,
        error_rate=0.0,
        target_url="http://test/api/v1/events",
        post=recording_post,
    )
    assert len(seen) == 2
    for envelope in seen:
        assert "event_id" in envelope
        assert "source" in envelope
        assert "kind" in envelope
        assert "payload" in envelope


def test_generate_load_rejects_invalid_error_rate() -> None:
    with pytest.raises(ValueError):
        generate_load(
            requests=10,
            error_rate=1.5,
            target_url="http://test",
            post=_make_fake_post(),
        )
    with pytest.raises(ValueError):
        generate_load(
            requests=10,
            error_rate=-0.1,
            target_url="http://test",
            post=_make_fake_post(),
        )


def test_load_result_summary_contains_counts() -> None:
    result = LoadResult(total=10, success_count=7, error_count=3, latencies_ms=[1.0, 2.0])
    s = result.summary()
    assert "10" in s
    assert "7" in s
    assert "3" in s

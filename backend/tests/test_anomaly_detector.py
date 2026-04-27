"""Rolling robust z-score anomaly detector."""
from datetime import UTC, datetime, timedelta

import pytest

from repopulse.anomaly.detector import Anomaly, Point, detect_zscore


def _series(values: list[float], *, step_seconds: int = 60) -> list[Point]:
    base = datetime(2026, 4, 27, 0, 0, 0, tzinfo=UTC)
    return [
        Point(timestamp=base + timedelta(seconds=i * step_seconds), value=v)
        for i, v in enumerate(values)
    ]


def test_detect_no_anomalies_in_flat_series() -> None:
    series = _series([10.0] * 50)
    assert detect_zscore(series, window=10) == []


def test_detect_finds_single_spike() -> None:
    values = [10.0] * 30 + [200.0]
    series = _series(values)
    anomalies = detect_zscore(series, window=10, series_name="cpu")
    assert len(anomalies) == 1
    assert anomalies[0].value == 200.0
    assert anomalies[0].series_name == "cpu"


def test_detect_returns_score_above_threshold() -> None:
    values = [10.0] * 30 + [500.0]
    anomalies = detect_zscore(_series(values), window=10, threshold=3.5)
    assert len(anomalies) == 1
    assert abs(anomalies[0].score) >= 3.5


def test_detect_severity_critical_above_double_threshold() -> None:
    values = [10.0] * 30 + [10000.0]
    anomalies = detect_zscore(_series(values), window=10, threshold=3.5)
    assert len(anomalies) == 1
    assert anomalies[0].severity == "critical"


def test_detect_severity_warning_at_threshold_band() -> None:
    """Build a small spike whose modified z-score is between threshold and 2*threshold.

    With this baseline, MAD = 0.2 and median = 10.0 → score = 3.3725 * (value - 10).
    Setting value = 11.5 gives score ≈ 5.06, which sits firmly in the
    warning band (≥ 3.5 and < 7.0).
    """
    base = [10.0, 11.0, 9.0, 10.5, 9.5, 10.2, 9.8, 10.1, 9.9, 10.0]
    values = base + [11.5]
    anomalies = detect_zscore(_series(values), window=10, threshold=3.5)
    assert anomalies and anomalies[0].severity == "warning"
    assert 3.5 <= abs(anomalies[0].score) < 7.0


def test_detect_silent_series_zero_mad_returns_no_anomalies() -> None:
    series = _series([5.0] * 50)
    assert detect_zscore(series, window=10) == []


def test_detect_does_not_emit_for_indices_before_window() -> None:
    series = _series([10.0, 1000.0] + [10.0] * 50)
    anomalies = detect_zscore(series, window=10)
    timestamps = {a.timestamp for a in anomalies}
    assert series[1].timestamp not in timestamps


def test_detect_seasonal_baseline_uses_same_period_offsets() -> None:
    """A recurring spike every 24 points must NOT register as anomalous when the
    baseline samples the SAME phase of the cycle."""
    values: list[float] = []
    for _ in range(5):
        values.extend([10.0] * 23 + [100.0])
    anomalies = detect_zscore(
        _series(values), window=4, threshold=3.5, seasonal_period=24
    )
    assert anomalies == []


def test_detect_seasonal_baseline_does_register_off_phase_spike() -> None:
    """An off-phase spike inside an otherwise seasonal series should still fire."""
    values: list[float] = []
    for _ in range(5):
        values.extend([10.0] * 23 + [100.0])
    values[24 * 4 + 5] = 500.0
    anomalies = detect_zscore(
        _series(values), window=4, threshold=3.5, seasonal_period=24
    )
    assert any(a.value == 500.0 for a in anomalies)


def test_detect_seasonal_baseline_with_noisy_baseline_uses_modified_zscore() -> None:
    """M3 review I4 follow-up: the off-phase test above passes via the MAD=0
    branch (baseline is perfectly silent). This test exercises the actual
    modified-z-score formula by introducing baseline noise so MAD > 0 at the
    seasonal phase, while still detecting an off-phase spike."""
    values: list[float] = []
    rng = [0.0, 0.3, -0.2, 0.1, -0.1, 0.2, -0.3, 0.0]
    # Per-cycle phase shift makes same-phase samples differ across cycles, so
    # the seasonal baseline window has nonzero MAD.
    for cycle in range(5):
        cycle_values = [
            10.0 + rng[(i + cycle) % len(rng)] for i in range(23)
        ] + [100.0]
        values.extend(cycle_values)
    # Off-phase spike during cycle 4, position 5.
    values[24 * 4 + 5] = 500.0
    anomalies = detect_zscore(
        _series(values), window=4, threshold=3.5, seasonal_period=24
    )
    spike_anomalies = [a for a in anomalies if a.value == 500.0]
    assert spike_anomalies, "expected the off-phase 500.0 spike to be detected"
    # The detection must come from the real modified-z-score path, not the
    # MAD=0 inf shortcut: baseline_mad must be strictly positive.
    assert spike_anomalies[0].baseline_mad > 0.0
    assert spike_anomalies[0].score != float("inf")


def test_detect_returns_anomaly_dataclass_with_baseline_fields() -> None:
    values = [10.0] * 30 + [200.0]
    a = detect_zscore(_series(values), window=10)[0]
    assert isinstance(a, Anomaly)
    assert a.baseline_median == 10.0
    assert a.baseline_mad >= 0.0


def test_detect_rejects_invalid_window() -> None:
    with pytest.raises(ValueError):
        detect_zscore([], window=0)
    with pytest.raises(ValueError):
        detect_zscore([], window=-1)


def test_detect_short_series_returns_empty() -> None:
    series = _series([1.0, 2.0, 3.0])
    assert detect_zscore(series, window=10) == []

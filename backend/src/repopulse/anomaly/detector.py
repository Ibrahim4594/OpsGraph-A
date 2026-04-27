"""Rolling robust z-score anomaly detection.

Uses the modified z-score from Iglewicz & Hoaglin (1993):
``z = 0.6745 * (x - median) / MAD``. Resistant to outliers in the
baseline window. With ``seasonal_period`` set, the baseline window
samples the SAME phase of the cycle (every ``period`` steps back)
instead of the contiguous prior points, so legitimate diurnal /
weekly spikes are suppressed.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Literal

_MZ_CONST = 0.6745


@dataclass(frozen=True)
class Point:
    timestamp: datetime
    value: float


@dataclass(frozen=True)
class Anomaly:
    timestamp: datetime
    value: float
    baseline_median: float
    baseline_mad: float
    score: float
    severity: Literal["warning", "critical"]
    series_name: str


def _baseline_indices(
    i: int, *, window: int, seasonal_period: int | None
) -> list[int]:
    if seasonal_period is None:
        return list(range(i - window, i))
    indices: list[int] = []
    for k in range(1, window + 1):
        idx = i - k * seasonal_period
        if idx < 0:
            break
        indices.append(idx)
    return indices


def _mad(values: list[float], med: float) -> float:
    return median(abs(v - med) for v in values)


def detect_zscore(
    series: Sequence[Point],
    *,
    window: int,
    threshold: float = 3.5,
    series_name: str = "default",
    seasonal_period: int | None = None,
) -> list[Anomaly]:
    """Return all points whose modified z-score against the rolling baseline
    meets ``|score| >= threshold``."""
    if window <= 0:
        raise ValueError(f"window must be > 0, got {window!r}")

    anomalies: list[Anomaly] = []
    if len(series) < window + 1:
        return anomalies

    for i in range(window, len(series)):
        idxs = _baseline_indices(i, window=window, seasonal_period=seasonal_period)
        if len(idxs) < 2:
            continue
        baseline_values = [series[j].value for j in idxs]
        med = median(baseline_values)
        mad = _mad(baseline_values, med)
        value = series[i].value

        if mad == 0.0:
            # Silent baseline: any deviation from the median is maximally
            # anomalous (modified z-score is undefined). Skip when the value
            # also matches the median (truly silent), otherwise emit a
            # critical-severity anomaly with an infinite score.
            if value == med:
                continue
            score = math.inf if value > med else -math.inf
        else:
            score = _MZ_CONST * (value - med) / mad
            if abs(score) < threshold:
                continue

        severity: Literal["warning", "critical"] = (
            "critical" if abs(score) >= 2 * threshold else "warning"
        )
        anomalies.append(
            Anomaly(
                timestamp=series[i].timestamp,
                value=series[i].value,
                baseline_median=med,
                baseline_mad=mad,
                score=score,
                severity=severity,
                series_name=series_name,
            )
        )
    return anomalies

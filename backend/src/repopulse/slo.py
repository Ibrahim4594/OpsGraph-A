"""SLO math: pure functions, no IO.

The functions here implement the formulas from the Google SRE Workbook
(chapter 5, "Alerting on SLOs"). They are deliberately side-effect-free
so they can be reused from tests, the synthetic load generator, and any
future alerting path without leaking infrastructure concerns.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class SLO:
    """A single Service Level Objective.

    ``target`` is the success-ratio objective expressed as a fraction in
    ``[0, 1]`` (e.g. ``0.999`` for 99.9 % availability).
    """

    target: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.target <= 1.0:
            raise ValueError(
                f"SLO target must be in [0, 1]; got {self.target!r}",
            )


def availability_sli(*, success_count: int, total_count: int) -> float:
    """Ratio of successful events to total events.

    Returns 1.0 when there is no traffic (vacuously meeting the SLO).
    Raises ``ValueError`` for negative counts or ``success_count > total_count``.
    """
    if success_count < 0 or total_count < 0:
        raise ValueError("counts must be non-negative")
    if success_count > total_count:
        raise ValueError("success_count cannot exceed total_count")
    if total_count == 0:
        return 1.0
    return success_count / total_count


def latency_sli(*, samples_ms: Sequence[float], threshold_ms: float) -> float:
    """Fraction of samples meeting the latency threshold (``<=`` is inclusive).

    Empty samples yield 1.0 (vacuously meeting the SLO).
    """
    if not samples_ms:
        return 1.0
    meeting = sum(1 for s in samples_ms if s <= threshold_ms)
    return meeting / len(samples_ms)


def error_budget(slo: SLO) -> float:
    """Allowed error fraction for the window: ``1 - target``."""
    return 1.0 - slo.target


def burn_rate(*, actual_error_rate: float, slo: SLO) -> float:
    """How fast the error budget is being consumed.

    A burn rate of 1.0 means the budget is being consumed at exactly the
    sustainable pace. >1.0 means burning faster than allowed; ``inf`` when
    the SLO target is 100% and any errors occur.
    """
    budget = error_budget(slo)
    if budget == 0.0:
        return 0.0 if actual_error_rate == 0.0 else math.inf
    return actual_error_rate / budget


def is_fast_burn(*, burn: float, threshold: float = 14.4) -> bool:
    """Fast-burn alert (Google SRE workbook 1h window default: 14.4×)."""
    return burn >= threshold


def is_slow_burn(*, burn: float, threshold: float = 6.0) -> bool:
    """Slow-burn alert (Google SRE workbook 6h window default: 6×)."""
    return burn >= threshold

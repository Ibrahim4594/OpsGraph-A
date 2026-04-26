"""SLO math: pure functions, no IO."""
import math

import pytest

from repopulse.slo import (
    SLO,
    availability_sli,
    burn_rate,
    error_budget,
    is_fast_burn,
    is_slow_burn,
    latency_sli,
)

# --- availability_sli ---------------------------------------------------------

def test_availability_sli_perfect() -> None:
    assert availability_sli(success_count=100, total_count=100) == 1.0


def test_availability_sli_half_failed() -> None:
    assert availability_sli(success_count=50, total_count=100) == 0.5


def test_availability_sli_zero_traffic_returns_one() -> None:
    """With no requests, availability is undefined; we choose 1.0 (vacuously true)."""
    assert availability_sli(success_count=0, total_count=0) == 1.0


def test_availability_sli_rejects_success_greater_than_total() -> None:
    with pytest.raises(ValueError):
        availability_sli(success_count=11, total_count=10)


def test_availability_sli_rejects_negative() -> None:
    with pytest.raises(ValueError):
        availability_sli(success_count=-1, total_count=10)


# --- latency_sli --------------------------------------------------------------

def test_latency_sli_all_under_threshold() -> None:
    assert latency_sli(samples_ms=[10.0, 20.0, 30.0], threshold_ms=100.0) == 1.0


def test_latency_sli_half_over_threshold() -> None:
    assert latency_sli(samples_ms=[10.0, 200.0, 30.0, 400.0], threshold_ms=100.0) == 0.5


def test_latency_sli_empty_samples_returns_one() -> None:
    assert latency_sli(samples_ms=[], threshold_ms=100.0) == 1.0


def test_latency_sli_boundary_inclusive() -> None:
    """A sample exactly at the threshold counts as meeting the SLO."""
    assert latency_sli(samples_ms=[100.0, 100.0], threshold_ms=100.0) == 1.0


# --- error_budget -------------------------------------------------------------

def test_error_budget_basic() -> None:
    assert error_budget(SLO(target=0.999)) == pytest.approx(0.001)


def test_error_budget_perfect_target_is_zero() -> None:
    assert error_budget(SLO(target=1.0)) == 0.0


def test_slo_target_must_be_in_range() -> None:
    with pytest.raises(ValueError):
        SLO(target=1.5)
    with pytest.raises(ValueError):
        SLO(target=-0.1)


# --- burn_rate ---------------------------------------------------------------

def test_burn_rate_at_budget_is_one() -> None:
    """If the actual error rate equals the budget, burn rate is exactly 1× (steady)."""
    slo = SLO(target=0.999)
    assert burn_rate(actual_error_rate=0.001, slo=slo) == pytest.approx(1.0)


def test_burn_rate_double_budget() -> None:
    slo = SLO(target=0.999)
    assert burn_rate(actual_error_rate=0.002, slo=slo) == pytest.approx(2.0)


def test_burn_rate_zero_errors() -> None:
    slo = SLO(target=0.999)
    assert burn_rate(actual_error_rate=0.0, slo=slo) == 0.0


def test_burn_rate_perfect_target_with_errors_is_inf() -> None:
    """A 100% target leaves zero budget, so any error rate is infinite burn."""
    slo = SLO(target=1.0)
    assert math.isinf(burn_rate(actual_error_rate=0.001, slo=slo))


def test_burn_rate_perfect_target_zero_errors_is_zero() -> None:
    slo = SLO(target=1.0)
    assert burn_rate(actual_error_rate=0.0, slo=slo) == 0.0


# --- burn-rate alert thresholds (Google SRE workbook) -------------------------

def test_is_fast_burn_default_threshold_14_4() -> None:
    assert is_fast_burn(burn=14.4) is True
    assert is_fast_burn(burn=14.5) is True
    assert is_fast_burn(burn=14.39) is False


def test_is_slow_burn_default_threshold_6_0() -> None:
    assert is_slow_burn(burn=6.0) is True
    assert is_slow_burn(burn=6.1) is True
    assert is_slow_burn(burn=5.99) is False

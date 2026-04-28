"""Shared pytest fixtures."""

from __future__ import annotations

import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Set before test modules import ``repopulse.main`` (so module ``app``).

    Ensures :func:`repopulse.telemetry.init_telemetry` picks
    ``InMemoryMetricReader`` instead of a periodic console exporter thread
    that survives past pytest's stdout teardown.
    """
    _ = config
    os.environ["REPOPULSE_UNDER_PYTEST"] = "1"


@pytest.fixture(autouse=True)
def _pipeline_api_secret_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test gets a configured pipeline API secret unless a test
    explicitly removes it (e.g. 503 coverage)."""
    monkeypatch.setenv("REPOPULSE_API_SHARED_SECRET", "test-pipeline-api-secret")

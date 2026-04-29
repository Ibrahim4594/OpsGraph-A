"""Shared pytest fixtures."""

from __future__ import annotations

import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Set before test modules import ``repopulse.main`` (so module ``app``).

    - ``REPOPULSE_UNDER_PYTEST=1`` ensures
      :func:`repopulse.telemetry.init_telemetry` picks
      ``InMemoryMetricReader`` instead of a periodic console exporter
      thread that survives past pytest's stdout teardown.
    - ``REPOPULSE_DATABASE_URL`` is set to a stub URL so
      :func:`repopulse.main.create_app` does not raise (T6 makes the DB
      URL mandatory for production). The engine is lazy — no socket
      opens until a route reaches it. Tests that drive orchestrator
      routes pass ``orchestrator=`` from
      ``tests._inmem_orchestrator.make_inmem_orchestrator``, so the
      stub URL is never actually dialled. The negative case (URL unset
      → RuntimeError) is asserted explicitly in
      ``tests/test_main_lifespan.py``.
    """
    _ = config
    os.environ["REPOPULSE_UNDER_PYTEST"] = "1"
    os.environ.setdefault(
        "REPOPULSE_DATABASE_URL",
        "postgresql+psycopg://stub:stub@localhost:1/stub",
    )


@pytest.fixture(autouse=True)
def _pipeline_api_secret_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test gets a configured pipeline API secret unless a test
    explicitly removes it (e.g. 503 coverage)."""
    monkeypatch.setenv("REPOPULSE_API_SHARED_SECRET", "test-pipeline-api-secret")

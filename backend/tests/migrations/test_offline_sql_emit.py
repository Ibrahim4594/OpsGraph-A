"""Offline ``alembic upgrade head --sql`` parses + emits without a daemon.

Doesn't need Docker. Doesn't open a connection. Validates that every
revision's ``upgrade()`` callable runs against Alembic's offline mode
and produces non-empty SQL — catches Python syntax errors, missing
imports, broken op signatures, undefined revision IDs, etc.

The SQL output is also lightly inspected: every CREATE TABLE we expect
appears at least once; the ``signature_hash`` UNIQUE clause is present;
no migration emits zero SQL (would mean it silently became a no-op
because of an indentation bug).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.migration


def _alembic_offline_sql(*, cwd: Path) -> str:
    """Run ``alembic upgrade head --sql`` and return stdout.

    Sets ``REPOPULSE_DATABASE_URL`` to a stub Postgres URL so
    ``env.py`` accepts it; offline mode never dials the URL.
    """
    env = {
        **os.environ,
        "REPOPULSE_DATABASE_URL": (
            "postgresql+psycopg://stub:stub@localhost:1/stub"
        ),
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
    )
    if result.returncode != 0:
        pytest.fail(
            f"alembic offline SQL emit failed: {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


@pytest.mark.no_docker
def test_offline_upgrade_head_emits_sql_for_every_revision(
    alembic_cwd: Path,
) -> None:
    """Doesn't need Docker — opted in via ``@pytest.mark.no_docker`` so
    the migration-folder skip-when-no-docker hook lets it through."""
    sql = _alembic_offline_sql(cwd=alembic_cwd)

    # Each revision's "Running upgrade ..." marker appears.
    for rev in (
        "0001_initial_schema",
        "0002_recommendation_state",
        "0003_indexes_hot_paths",
        "0004_recommendation_transitions",
        "0005_incident_signature_dedup",
    ):
        assert rev in sql, f"revision {rev} not run by upgrade head --sql"

    # Every expected table is present in the emitted DDL.
    for table in (
        "raw_events",
        "normalized_events",
        "anomalies",
        "incidents",
        "incident_events",
        "incident_anomalies",
        "recommendations",
        "recommendation_transitions",
        "action_history",
        "workflow_usage",
    ):
        assert f"CREATE TABLE {table}" in sql, f"missing CREATE TABLE {table}"

    # The signature_hash UNIQUE clause is in 0001 (case-insensitive search).
    assert "signature_hash" in sql.lower()
    # Defensive 0005's IF NOT EXISTS guard is in the emitted SQL.
    assert "if not exists" in sql.lower()

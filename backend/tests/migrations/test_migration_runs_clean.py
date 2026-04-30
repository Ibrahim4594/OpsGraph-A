"""``alembic upgrade head`` on a fresh DB exits 0 and produces every
expected table + index.

Skipped if Docker isn't reachable (see ``conftest.py``).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.migration


_EXPECTED_TABLES = {
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
}

_EXPECTED_INDEXES = {
    "ix_raw_events_received_at",
    "ix_normalized_events_received_at",
    "ix_normalized_events_occurred_at",
    "ix_anomalies_timestamp_series",
    "ix_incidents_started_at",
    "ix_incidents_ended_at",
    "ix_recommendations_state_action_category",
    "ix_recommendations_incident_id",
    "ix_recommendation_transitions_rec_at",
    "ix_action_history_at",
    "ix_action_history_kind",
    "ix_workflow_usage_received_at",
    "ix_workflow_usage_repository_workflow",
}


def _alembic(args: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    """Run ``alembic`` and return stdout. Raises on non-zero exit."""
    full_env = {**os.environ, **env}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=full_env,
    )
    if result.returncode != 0:
        pytest.fail(
            "alembic failed with code "
            f"{result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


def test_upgrade_head_creates_every_expected_table_and_index(
    clean_db: str, alembic_cwd: Path
) -> None:
    """``alembic upgrade head`` against an empty DB lands all 5 revisions
    cleanly and produces every table + index the model layer declares.
    """
    from sqlalchemy import create_engine, inspect

    _alembic(["upgrade", "head"], cwd=alembic_cwd, env={"REPOPULSE_DATABASE_URL": clean_db})

    engine = create_engine(clean_db, future=True)
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert _EXPECTED_TABLES.issubset(tables), (
        f"missing tables: {_EXPECTED_TABLES - tables}"
    )

    indexes: set[str] = set()
    for table in tables:
        for idx in insp.get_indexes(table):
            if idx.get("name"):
                indexes.add(idx["name"])  # type: ignore[arg-type]
    assert _EXPECTED_INDEXES.issubset(indexes), (
        f"missing indexes: {_EXPECTED_INDEXES - indexes}"
    )

    # signature_hash UNIQUE constraint exists on incidents.
    uniques = insp.get_unique_constraints("incidents")
    sig_uniques = [u for u in uniques if u["column_names"] == ["signature_hash"]]
    assert sig_uniques, f"missing UNIQUE(signature_hash); got {uniques}"

    engine.dispose()


def test_alembic_current_after_upgrade_is_head(
    clean_db: str, alembic_cwd: Path
) -> None:
    """``alembic current`` after upgrade reports the head revision."""
    _alembic(["upgrade", "head"], cwd=alembic_cwd, env={"REPOPULSE_DATABASE_URL": clean_db})
    out = _alembic(
        ["current"], cwd=alembic_cwd, env={"REPOPULSE_DATABASE_URL": clean_db}
    )
    assert "0005_incident_signature_dedup" in out


def test_upgrade_is_idempotent_when_run_twice(
    clean_db: str, alembic_cwd: Path
) -> None:
    """Running ``upgrade head`` a second time is a no-op (no migrations to run)."""
    _alembic(
        ["upgrade", "head"],
        cwd=alembic_cwd,
        env={"REPOPULSE_DATABASE_URL": clean_db},
    )
    out = _alembic(
        ["upgrade", "head"],
        cwd=alembic_cwd,
        env={"REPOPULSE_DATABASE_URL": clean_db},
    )
    # No "Running upgrade" lines on the second invocation.
    assert "Running upgrade" not in out

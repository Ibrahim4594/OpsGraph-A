"""Per-revision reversibility: upgrade → downgrade -1 → upgrade preserves schema.

For each revision in 0001..head, this test:

1. ``alembic upgrade <prev>`` — land everything below the target.
2. ``alembic upgrade <rev>`` — apply target.
3. Capture ``inspect(engine)`` schema fingerprint.
4. ``alembic downgrade -1`` — revert target.
5. ``alembic upgrade head`` — re-apply target (and anything above it).
6. Re-capture fingerprint; assert no schema drift.

Defensive revisions 0002–0005 have intentional no-op downgrades on
fresh DBs (see their docstrings + the rollback matrix in the milestone
plan). For those revisions we assert the schema after step (5) is a
**superset** of the schema after step (3) — the downgrade left the
0001-owned objects in place, the upgrade didn't fail.

0001 has a real reversible downgrade (drops every table). For 0001 we
upgrade, downgrade, then upgrade again and assert tables exist again.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.migration

_REVISIONS = [
    "0001_initial_schema",
    "0002_recommendation_state",
    "0003_indexes_hot_paths",
    "0004_recommendation_transitions",
    "0005_incident_signature_dedup",
]


def _alembic(args: list[str], *, cwd: Path, env: dict[str, str]) -> str:
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
            f"alembic failed: {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


def _schema_fingerprint(url: str) -> dict[str, set[str]]:
    """Capture a comparable schema snapshot.

    Returns a dict ``{table_name: {column_names...}}`` plus a special
    key ``__indexes__`` mapping to the union of all index names. Two
    fingerprints comparing equal means no observable schema drift.
    """
    from sqlalchemy import create_engine, inspect

    engine = create_engine(url, future=True)
    insp = inspect(engine)
    fp: dict[str, set[str]] = {}
    indexes: set[str] = set()
    for t in insp.get_table_names():
        fp[t] = {c["name"] for c in insp.get_columns(t)}
        for idx in insp.get_indexes(t):
            if idx.get("name"):
                indexes.add(idx["name"])  # type: ignore[arg-type]
    fp["__indexes__"] = indexes
    engine.dispose()
    return fp


def test_revision_0001_full_reversibility(
    clean_db: str, alembic_cwd: Path
) -> None:
    """0001 has a real downgrade (drops tables). Verify upgrade →
    downgrade → upgrade is idempotent."""
    env = {"REPOPULSE_DATABASE_URL": clean_db}
    _alembic(["upgrade", "0001_initial_schema"], cwd=alembic_cwd, env=env)
    fp_after_first_upgrade = _schema_fingerprint(clean_db)
    assert "raw_events" in fp_after_first_upgrade

    _alembic(["downgrade", "base"], cwd=alembic_cwd, env=env)
    fp_after_downgrade = _schema_fingerprint(clean_db)
    # Public schema empty (alembic_version is its own table; tolerated).
    leftover = set(fp_after_downgrade) - {"alembic_version", "__indexes__"}
    assert leftover == set(), f"downgrade left tables behind: {leftover}"

    _alembic(["upgrade", "0001_initial_schema"], cwd=alembic_cwd, env=env)
    fp_after_redo = _schema_fingerprint(clean_db)
    assert fp_after_redo == fp_after_first_upgrade


@pytest.mark.parametrize("revision", _REVISIONS[1:])
def test_defensive_revision_downgrade_is_safe_noop_on_fresh_db(
    revision: str, clean_db: str, alembic_cwd: Path
) -> None:
    """0002–0005 have intentional no-op downgrades on fresh DBs.

    Verify: upgrade past the revision, downgrade -1, upgrade head again.
    The schema before and after must be identical — proves the revision
    is harmless to fresh DBs in BOTH directions.
    """
    env = {"REPOPULSE_DATABASE_URL": clean_db}
    _alembic(["upgrade", revision], cwd=alembic_cwd, env=env)
    fp_before = _schema_fingerprint(clean_db)

    _alembic(["downgrade", "-1"], cwd=alembic_cwd, env=env)
    fp_after_downgrade = _schema_fingerprint(clean_db)
    # Defensive downgrade is a no-op: nothing the prior revision created
    # should disappear (the prior revision was 0001 for 0002, etc., and
    # all of 0001's objects must remain).
    for table, cols in fp_before.items():
        if table == "__indexes__":
            continue
        if table == "alembic_version":
            continue
        assert table in fp_after_downgrade, (
            f"{revision} downgrade unexpectedly dropped table {table!r}"
        )
        assert cols.issubset(fp_after_downgrade[table]), (
            f"{revision} downgrade unexpectedly dropped columns from {table}: "
            f"missing {cols - fp_after_downgrade[table]}"
        )

    _alembic(["upgrade", "head"], cwd=alembic_cwd, env=env)
    fp_after_redo = _schema_fingerprint(clean_db)
    assert fp_after_redo == fp_before, (
        f"schema drift around {revision}: "
        f"missing={fp_before.keys() - fp_after_redo.keys()}, "
        f"extra={fp_after_redo.keys() - fp_before.keys()}"
    )

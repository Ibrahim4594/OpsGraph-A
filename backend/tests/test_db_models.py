"""Unit tests for the ORM model layer (M2.0 task 3).

No database, no Docker. We assert structural shape:

- All 8 model classes register on the shared metadata.
- Both bridge tables (``incident_events``, ``incident_anomalies``)
  register too.
- Each enum-like text column has the matching CHECK constraint.
- Hot-path indexes exist (received_at on normalized_events,
  (timestamp, series_name) on anomalies, (state, action_category) on
  recommendations, etc.).
- The 1:1 normalized_events ↔ raw_events FK is declared.
- Naming convention is honored — every constraint/index name is
  predictable from the convention in ``db/base.py``.

Integration tests (M2.0 task 10) will exercise the schema against a real
Postgres via Testcontainers. T3 only validates the static shape.
"""
from __future__ import annotations

from sqlalchemy import Table, UniqueConstraint

from repopulse.db.base import Base, metadata
from repopulse.db.models import (  # noqa: F401 — side-effect import registers models
    ActionHistoryORM,
    AnomalyORM,
    IncidentORM,
    NormalizedEventORM,
    RawEventORM,
    RecommendationORM,
    RecommendationTransitionORM,
    WorkflowUsageORM,
    incident_anomalies,
    incident_events,
)

EXPECTED_TABLES: set[str] = {
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


def test_all_models_registered_on_shared_metadata() -> None:
    """Importing ``db.models`` registers every model on ``Base.metadata``."""
    assert Base.metadata is metadata
    actual = set(metadata.tables.keys())
    assert actual >= EXPECTED_TABLES, (
        f"missing tables: {EXPECTED_TABLES - actual}"
    )


def test_raw_events_pk_is_event_id() -> None:
    table = metadata.tables["raw_events"]
    pk_cols = [c.name for c in table.primary_key.columns]
    assert pk_cols == ["event_id"]


def test_normalized_events_pk_and_fk_to_raw() -> None:
    """Strict 1:1 with raw_events: shared PK + FK."""
    table = metadata.tables["normalized_events"]
    pk_cols = [c.name for c in table.primary_key.columns]
    assert pk_cols == ["event_id"]
    fks = list(table.foreign_keys)
    assert len(fks) == 1
    assert fks[0].column.table.name == "raw_events"
    assert fks[0].column.name == "event_id"


def _check_constraint_names(table: Table) -> set[str]:
    """Collect CHECK-constraint names as plain strings.

    SQLAlchemy types ``Constraint.name`` as ``str | None | _NoneName`` which
    mypy strict refuses to use in ``in`` operators. Coerce here.
    """
    return {
        str(c.name) for c in table.constraints
        if hasattr(c, "sqltext") and c.name is not None
    }


def test_normalized_events_severity_check_constraint() -> None:
    table = metadata.tables["normalized_events"]
    check_names = _check_constraint_names(table)
    # CheckConstraints get a name based on the project's naming convention.
    assert any("severity" in n for n in check_names)


def test_normalized_events_received_at_indexed() -> None:
    table = metadata.tables["normalized_events"]
    idx_columns = {tuple(c.name for c in idx.columns) for idx in table.indexes}
    assert ("received_at",) in idx_columns


def test_anomalies_compound_index_timestamp_series() -> None:
    table = metadata.tables["anomalies"]
    idx_columns = {tuple(c.name for c in idx.columns) for idx in table.indexes}
    assert ("timestamp", "series_name") in idx_columns


def test_incidents_started_and_ended_indexed() -> None:
    table = metadata.tables["incidents"]
    idx_columns = {tuple(c.name for c in idx.columns) for idx in table.indexes}
    assert ("started_at",) in idx_columns
    assert ("ended_at",) in idx_columns


def test_incident_bridge_tables_have_composite_pk() -> None:
    for name, expected in (
        ("incident_events", {"incident_id", "event_id"}),
        ("incident_anomalies", {"incident_id", "anomaly_id"}),
    ):
        bridge: Table = metadata.tables[name]
        pk_cols = {c.name for c in bridge.primary_key.columns}
        assert pk_cols == expected, f"{name} PK mismatch: {pk_cols}"
        # ON DELETE CASCADE on both FKs so dropping an incident cleans up.
        for fk in bridge.foreign_keys:
            assert fk.ondelete == "CASCADE"


def test_recommendations_state_action_category_check_and_index() -> None:
    table = metadata.tables["recommendations"]
    # CHECK constraints exist (named via the naming convention).
    names = _check_constraint_names(table)
    assert any("action_category" in n for n in names)
    assert any("risk_level" in n for n in names)
    assert any("state" in n for n in names)
    # Compound index for the inbox query.
    idx_columns = {tuple(c.name for c in idx.columns) for idx in table.indexes}
    assert ("state", "action_category") in idx_columns


def test_recommendation_transitions_audit_index() -> None:
    table = metadata.tables["recommendation_transitions"]
    idx_columns = {tuple(c.name for c in idx.columns) for idx in table.indexes}
    assert ("recommendation_id", "at") in idx_columns


def test_action_history_kind_check_and_at_index() -> None:
    table = metadata.tables["action_history"]
    names = _check_constraint_names(table)
    assert any("kind" in n for n in names)
    idx_columns = {tuple(c.name for c in idx.columns) for idx in table.indexes}
    assert ("at",) in idx_columns
    assert ("kind",) in idx_columns


def test_action_history_recommendation_fk_nullable() -> None:
    """workflow-run entries may not have a recommendation_id."""
    table = metadata.tables["action_history"]
    rec_col = table.columns["recommendation_id"]
    assert rec_col.nullable is True


def test_workflow_usage_unique_run_id_per_repository() -> None:
    table = metadata.tables["workflow_usage"]
    uniques = [c for c in table.constraints if isinstance(c, UniqueConstraint)]
    assert any(
        {col.name for col in u.columns} == {"run_id", "repository"}
        for u in uniques
    ), f"missing UNIQUE(run_id, repository); got {uniques}"


def test_no_orm_imports_from_route_layer() -> None:
    """T3 constraint: ORM must not leak into the API/route layer.

    None of the existing ``repopulse.api.*`` modules should import from
    ``repopulse.db.models``. (The orchestrator facade in T5 will be the
    only consumer.)
    """
    import repopulse.api.actions as actions_mod
    import repopulse.api.events as events_mod
    import repopulse.api.incidents as incidents_mod
    import repopulse.api.recommendations as recommendations_mod
    import repopulse.api.slo as slo_mod

    for module in (
        events_mod,
        incidents_mod,
        recommendations_mod,
        actions_mod,
        slo_mod,
    ):
        # Crudely scan the module's top-level globals for ORM types.
        leaked = [
            name
            for name in vars(module)
            if name.endswith("ORM")
        ]
        assert not leaked, f"{module.__name__} imports ORM types: {leaked}"


def test_naming_convention_applied_to_indexes() -> None:
    """Sanity: explicit ``Index('ix_...')`` names follow the convention pattern."""
    seen_ix_names: set[str] = set()
    for table in metadata.tables.values():
        for idx in table.indexes:
            if idx.name and idx.name.startswith("ix_"):
                seen_ix_names.add(idx.name)
    # Must have many; check a couple of expected names exist.
    assert "ix_normalized_events_received_at" in seen_ix_names
    assert "ix_anomalies_timestamp_series" in seen_ix_names
    assert "ix_recommendations_state_action_category" in seen_ix_names

"""Defensive CREATE INDEX IF NOT EXISTS for the dashboard hot paths.

Revision ID: 0003_indexes_hot_paths
Revises: 0002_recommendation_state
Create Date: 2026-04-29

On a fresh v2.0.0 database every index this revision would create
already ships in :mod:`migrations.versions.0001_initial_schema`. The
``CREATE INDEX IF NOT EXISTS`` guards make this revision a **no-op
there**.

Indexes covered (all idempotent on fresh DBs):
- ``ix_normalized_events_received_at`` — SLO query hot path
- ``ix_anomalies_timestamp_series`` — correlate() scan
- ``ix_incidents_started_at`` / ``ix_incidents_ended_at`` — dashboard
- ``ix_recommendations_state_action_category`` — inbox query
- ``ix_action_history_at`` — audit feed
- UNIQUE ``run_id_repository`` on ``workflow_usage`` — idempotency

The downgrade is **also a no-op on fresh DBs** because the indexes are
owned by 0001. Older deployments that need to drop them manually after
a rollback can do so via standard ``DROP INDEX`` — but that's a
performance regression, not a correctness fix.
"""
from __future__ import annotations

from alembic import op

revision = "0003_indexes_hot_paths"
down_revision: str | None = "0002_recommendation_state"
branch_labels: str | None = None
depends_on: str | None = None


_INDEX_DEFS: list[tuple[str, str]] = [
    (
        "ix_normalized_events_received_at",
        "CREATE INDEX IF NOT EXISTS ix_normalized_events_received_at "
        "ON normalized_events (received_at)",
    ),
    (
        "ix_anomalies_timestamp_series",
        "CREATE INDEX IF NOT EXISTS ix_anomalies_timestamp_series "
        "ON anomalies (timestamp, series_name)",
    ),
    (
        "ix_incidents_started_at",
        "CREATE INDEX IF NOT EXISTS ix_incidents_started_at "
        "ON incidents (started_at)",
    ),
    (
        "ix_incidents_ended_at",
        "CREATE INDEX IF NOT EXISTS ix_incidents_ended_at "
        "ON incidents (ended_at)",
    ),
    (
        "ix_recommendations_state_action_category",
        "CREATE INDEX IF NOT EXISTS ix_recommendations_state_action_category "
        "ON recommendations (state, action_category)",
    ),
    (
        "ix_action_history_at",
        "CREATE INDEX IF NOT EXISTS ix_action_history_at "
        "ON action_history (at)",
    ),
]


def upgrade() -> None:
    for _name, sql in _INDEX_DEFS:
        op.execute(sql)
    # Workflow usage UNIQUE — also IF NOT EXISTS because 0001 already
    # created it as a UNIQUE constraint (which Postgres backs with a
    # unique index of the same name).
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'run_id_repository'
            ) THEN
                ALTER TABLE workflow_usage
                    ADD CONSTRAINT run_id_repository
                    UNIQUE (run_id, repository);
            END IF;
        END$$;
        """
    )


def downgrade() -> None:
    """Intentional no-op.

    All indexes addressed here are owned by 0001 on fresh DBs. Dropping
    them in downgrade would punch holes in the v2.0 baseline. See the
    rollback matrix in
    ``docs/superpowers/plans/milestone-2.0-storage-plan.md`` §5.
    """

"""Defensive CREATE TABLE ``recommendation_transitions`` (existing-deployment-only).

Revision ID: 0004_recommendation_transitions
Revises: 0003_indexes_hot_paths
Create Date: 2026-04-29

On a fresh v2.0.0 database the ``recommendation_transitions`` table
already ships in :mod:`migrations.versions.0001_initial_schema`. This
revision is a **no-op there** via ``CREATE TABLE IF NOT EXISTS`` /
``CREATE INDEX IF NOT EXISTS``.

The revision exists for older deployments (pre-M4) that lacked the
audit table; running ``alembic upgrade head`` on those brings them in
line with v2.0.

The downgrade is **a no-op on fresh DBs**: the table is owned by 0001
and dropping it here would destroy v2.0 audit data. Older deployments
that genuinely created the table here can drop it manually after a
``pg_dump`` snapshot.
"""
from __future__ import annotations

from alembic import op

revision = "0004_recommendation_transitions"
down_revision: str | None = "0003_indexes_hot_paths"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS recommendation_transitions (
            id UUID PRIMARY KEY,
            recommendation_id UUID NOT NULL REFERENCES recommendations(recommendation_id) ON DELETE CASCADE,
            from_state VARCHAR(16) NOT NULL,
            to_state VARCHAR(16) NOT NULL,
            actor VARCHAR(128) NOT NULL,
            reason TEXT NULL,
            at TIMESTAMP WITH TIME ZONE NOT NULL,
            CONSTRAINT from_state_in_set
                CHECK (from_state IN ('pending','approved','rejected','observed')),
            CONSTRAINT to_state_in_set
                CHECK (to_state IN ('pending','approved','rejected','observed'))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_recommendation_transitions_rec_at "
        "ON recommendation_transitions (recommendation_id, at)"
    )


def downgrade() -> None:
    """Intentional no-op.

    The ``recommendation_transitions`` table is owned by 0001 on fresh
    DBs. Dropping it here would corrupt the v2.0 baseline. See the
    rollback matrix in
    ``docs/superpowers/plans/milestone-2.0-storage-plan.md`` §5.
    """

"""Defensive ADD COLUMN ``recommendations.state`` (existing-deployment-only).

Revision ID: 0002_recommendation_state
Revises: 0001_initial_schema
Create Date: 2026-04-29

On a fresh v2.0.0 database the ``state`` column + CHECK constraint
already ship in :mod:`migrations.versions.0001_initial_schema`. This
revision is a **no-op there**: the IF NOT EXISTS guard skips both the
ADD COLUMN and the ADD CONSTRAINT.

The revision exists only for older deployments that pre-dated the
column landing in the model. Such deployments may have run a hand-rolled
M3 schema; this migration brings them in line with v2.0.

The downgrade is **a no-op on fresh DBs** (the column is owned by 0001
and must not be dropped here — see the rollback matrix). On older
deployments where this revision *did* add the column, the operator can
manually run ``ALTER TABLE recommendations DROP COLUMN state`` after a
``pg_dump`` snapshot. We refuse to do it automatically because the
state column is load-bearing for the M4 transitions UX.
"""
from __future__ import annotations

from alembic import op

revision = "0002_recommendation_state"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'recommendations'
                  AND column_name = 'state'
            ) THEN
                ALTER TABLE recommendations
                    ADD COLUMN state VARCHAR(16) NOT NULL
                    DEFAULT 'pending';

                ALTER TABLE recommendations
                    ADD CONSTRAINT state_in_set
                    CHECK (state IN ('pending','approved','rejected','observed'));
            END IF;
        END$$;
        """
    )


def downgrade() -> None:
    """Intentional no-op.

    The ``state`` column is owned by ``0001_initial_schema`` on fresh DBs.
    Dropping it here would corrupt the v2.0 baseline. Older deployments
    that need to revert to pre-M3 behavior should drop the column
    manually after a snapshot — see ``docs/superpowers/plans/
    milestone-2.0-storage-plan.md`` §5.
    """

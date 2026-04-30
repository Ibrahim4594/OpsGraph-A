"""Defensive ADD COLUMN ``incidents.signature_hash`` + UNIQUE (existing-deployment-only).

Revision ID: 0005_incident_signature_dedup
Revises: 0004_recommendation_transitions
Create Date: 2026-04-29

On a fresh v2.0.0 database the ``signature_hash`` column + UNIQUE
constraint already ship in :mod:`migrations.versions.0001_initial_schema`.
This revision is a **no-op there** — the IF NOT EXISTS guards skip the
ADD COLUMN, the backfill (no rows would match the temporary placeholder),
and the ADD CONSTRAINT.

The revision exists only for older deployments (pre-T3 amend, where
``signature_hash`` was *not* on ``IncidentORM`` and incidents were
deduped via the in-memory ``_seen_keys`` LRU). For those deployments,
running ``alembic upgrade head`` performs:

1. ADD COLUMN ``signature_hash VARCHAR(64) NULL``
2. Backfill — populate every existing row with a deterministic hash
   computed in-DB from ``(incident_id, started_at, ended_at)`` (lossy
   substitute for the in-memory key, but unique per existing row).
3. ALTER COLUMN ... SET NOT NULL.
4. ADD CONSTRAINT signature_hash UNIQUE (signature_hash).

Backfill rationale: we cannot reproduce the v1.1 in-memory
``_incident_key`` (which hashed event_ids + anomaly fingerprints) from
within Postgres without reading the bridge tables — and the bridge
tables didn't exist in older deployments either. ``incident_id`` is
already unique, so hashing it produces a unique signature per row; the
real signature_hash semantics (content-based dedup of *future*
incidents) takes effect from the next ``evaluate()`` onwards.

The downgrade is **a no-op on fresh DBs** (column owned by 0001). On
older deployments where this revision genuinely added the column, the
operator can manually drop it after a ``pg_dump`` snapshot — but doing
so reverts incident dedup to the in-memory LRU, which is gone in v2.0.
"""
from __future__ import annotations

from alembic import op

revision = "0005_incident_signature_dedup"
down_revision: str | None = "0004_recommendation_transitions"
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
                WHERE table_name = 'incidents'
                  AND column_name = 'signature_hash'
            ) THEN
                ALTER TABLE incidents
                    ADD COLUMN signature_hash VARCHAR(64) NULL;

                -- Backfill placeholder. md5() is built into Postgres
                -- (no pgcrypto extension required) and yields 32 chars;
                -- we double it so the result fits in VARCHAR(64) and
                -- mirrors the SHA-256 hex shape that future evaluate()
                -- calls produce. The placeholder never collides with a
                -- real signature because md5(incident_id::text)
                -- is unique per incident.
                UPDATE incidents
                SET signature_hash =
                    md5(incident_id::text)
                    || md5(incident_id::text || ':backfill');

                ALTER TABLE incidents
                    ALTER COLUMN signature_hash SET NOT NULL;

                ALTER TABLE incidents
                    ADD CONSTRAINT signature_hash UNIQUE (signature_hash);
            END IF;
        END$$;
        """
    )


def downgrade() -> None:
    """Intentional no-op.

    The ``signature_hash`` column + UNIQUE are owned by 0001 on fresh
    DBs. Dropping them here would corrupt the v2.0 dedup invariant. See
    the rollback matrix in
    ``docs/superpowers/plans/milestone-2.0-storage-plan.md`` §5.
    """

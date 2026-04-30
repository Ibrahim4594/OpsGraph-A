"""M2.0 baseline schema — all 9 tables for v2.0.0-storage.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-29

This is the v2.0.0 baseline. A fresh database (CI, dev, brand-new prod)
gets the entire schema from this single revision — including
``incidents.signature_hash`` + UNIQUE, which migration 0005 only
re-applies on **older deployments** that pre-dated the column landing
in the model.

DDL is written explicitly (no ``Base.metadata.create_all`` call) so the
revision is a self-contained, auditable artefact. The shape mirrors
``repopulse.db.models.*`` exactly as of 2026-04-29; T7 reversibility
tests exercise upgrade/downgrade round-trips.

Naming convention: explicit names per ``repopulse.db.base.NAMING_CONVENTION``
where SQLAlchemy would otherwise auto-name CHECK / UNIQUE constraints,
so downgrade can drop them by name.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Alembic identifiers.
revision = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ---- raw_events ---------------------------------------------------------
    op.create_table(
        "raw_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_raw_events_received_at", "raw_events", ["received_at"]
    )

    # ---- normalized_events --------------------------------------------------
    op.create_table(
        "normalized_events",
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_events.event_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("attributes", postgresql.JSONB, nullable=False),
        sa.CheckConstraint(
            "severity IN ('info','warning','error','critical')",
            name="severity_in_set",
        ),
    )
    op.create_index(
        "ix_normalized_events_received_at",
        "normalized_events",
        ["received_at"],
    )
    op.create_index(
        "ix_normalized_events_occurred_at",
        "normalized_events",
        ["occurred_at"],
    )

    # ---- anomalies ----------------------------------------------------------
    op.create_table(
        "anomalies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("baseline_median", sa.Float, nullable=False),
        sa.Column("baseline_mad", sa.Float, nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("series_name", sa.String(128), nullable=False),
        sa.CheckConstraint(
            "severity IN ('warning','critical')",
            name="anomaly_severity_in_set",
        ),
    )
    op.create_index(
        "ix_anomalies_timestamp_series",
        "anomalies",
        ["timestamp", "series_name"],
    )

    # ---- incidents ----------------------------------------------------------
    op.create_table(
        "incidents",
        sa.Column(
            "incident_id", postgresql.UUID(as_uuid=True), primary_key=True
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sources", postgresql.JSONB, nullable=False),
        sa.Column("signature_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("signature_hash", name="signature_hash"),
    )
    op.create_index(
        "ix_incidents_started_at", "incidents", ["started_at"]
    )
    op.create_index("ix_incidents_ended_at", "incidents", ["ended_at"])

    # ---- incident_events (M:M bridge) --------------------------------------
    op.create_table(
        "incident_events",
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.incident_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "normalized_events.event_id", ondelete="CASCADE"
            ),
            primary_key=True,
        ),
    )

    # ---- incident_anomalies (M:M bridge) -----------------------------------
    op.create_table(
        "incident_anomalies",
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.incident_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "anomaly_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("anomalies.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # ---- recommendations ----------------------------------------------------
    op.create_table(
        "recommendations",
        sa.Column(
            "recommendation_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.incident_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action_category", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("evidence_trace", postgresql.JSONB, nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.CheckConstraint(
            "action_category IN ('observe','triage','escalate','rollback')",
            name="action_category_in_set",
        ),
        sa.CheckConstraint(
            "risk_level IN ('low','medium','high')",
            name="risk_level_in_set",
        ),
        sa.CheckConstraint(
            "state IN ('pending','approved','rejected','observed')",
            name="state_in_set",
        ),
    )
    op.create_index(
        "ix_recommendations_state_action_category",
        "recommendations",
        ["state", "action_category"],
    )
    op.create_index(
        "ix_recommendations_incident_id",
        "recommendations",
        ["incident_id"],
    )

    # ---- recommendation_transitions -----------------------------------------
    op.create_table(
        "recommendation_transitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "recommendation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "recommendations.recommendation_id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("from_state", sa.String(16), nullable=False),
        sa.Column("to_state", sa.String(16), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "from_state IN ('pending','approved','rejected','observed')",
            name="from_state_in_set",
        ),
        sa.CheckConstraint(
            "to_state IN ('pending','approved','rejected','observed')",
            name="to_state_in_set",
        ),
    )
    op.create_index(
        "ix_recommendation_transitions_rec_at",
        "recommendation_transitions",
        ["recommendation_id", "at"],
    )

    # ---- action_history -----------------------------------------------------
    op.create_table(
        "action_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column(
            "recommendation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "recommendations.recommendation_id", ondelete="SET NULL"
            ),
            nullable=True,
        ),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.CheckConstraint(
            "kind IN ('approve','reject','observe','workflow-run')",
            name="kind_in_set",
        ),
    )
    op.create_index("ix_action_history_at", "action_history", ["at"])
    op.create_index("ix_action_history_kind", "action_history", ["kind"])

    # ---- workflow_usage -----------------------------------------------------
    op.create_table(
        "workflow_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_name", sa.String(128), nullable=False),
        sa.Column("run_id", sa.Integer, nullable=False),
        sa.Column("duration_seconds", sa.Float, nullable=False),
        sa.Column("conclusion", sa.String(32), nullable=False),
        sa.Column("repository", sa.String(255), nullable=False),
        sa.Column("cost_estimate_usd", sa.Float, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "run_id", "repository", name="run_id_repository"
        ),
    )
    op.create_index(
        "ix_workflow_usage_received_at",
        "workflow_usage",
        ["received_at"],
    )
    op.create_index(
        "ix_workflow_usage_repository_workflow",
        "workflow_usage",
        ["repository", "workflow_name"],
    )


def downgrade() -> None:
    """Drop all tables in reverse FK order.

    DATA-LOSS: every row in every v2.0 table is destroyed. Document in
    ``docs/superpowers/plans/milestone-2.0-storage-plan.md`` §5; the
    M3.2 ops runbook surfaces this to the operator.
    """
    op.drop_index(
        "ix_workflow_usage_repository_workflow", table_name="workflow_usage"
    )
    op.drop_index(
        "ix_workflow_usage_received_at", table_name="workflow_usage"
    )
    op.drop_table("workflow_usage")

    op.drop_index("ix_action_history_kind", table_name="action_history")
    op.drop_index("ix_action_history_at", table_name="action_history")
    op.drop_table("action_history")

    op.drop_index(
        "ix_recommendation_transitions_rec_at",
        table_name="recommendation_transitions",
    )
    op.drop_table("recommendation_transitions")

    op.drop_index(
        "ix_recommendations_incident_id", table_name="recommendations"
    )
    op.drop_index(
        "ix_recommendations_state_action_category",
        table_name="recommendations",
    )
    op.drop_table("recommendations")

    op.drop_table("incident_anomalies")
    op.drop_table("incident_events")

    op.drop_index("ix_incidents_ended_at", table_name="incidents")
    op.drop_index("ix_incidents_started_at", table_name="incidents")
    op.drop_table("incidents")

    op.drop_index("ix_anomalies_timestamp_series", table_name="anomalies")
    op.drop_table("anomalies")

    op.drop_index(
        "ix_normalized_events_occurred_at", table_name="normalized_events"
    )
    op.drop_index(
        "ix_normalized_events_received_at", table_name="normalized_events"
    )
    op.drop_table("normalized_events")

    op.drop_index("ix_raw_events_received_at", table_name="raw_events")
    op.drop_table("raw_events")

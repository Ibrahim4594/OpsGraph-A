"""``anomalies`` — detector output rows.

The v1.1 :class:`repopulse.anomaly.detector.Anomaly` is anonymous (no id
field on the dataclass). We add a surrogate UUID ``id`` PK so the row is
addressable for joins (incident_anomalies bridge) and audit traces.

Indexes target the correlation hot path: ``correlate()`` walks events +
anomalies sorted by time; ``(timestamp, series_name)`` is the most
selective compound index for that scan.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Float, Index, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from repopulse.db.base import Base

#: Allowed values for ``anomalies.severity``. Mirrors the detector's
#: ``Literal["warning", "critical"]``.
ANOMALY_SEVERITY_VALUES: tuple[str, ...] = ("warning", "critical")


class AnomalyORM(Base):
    __tablename__ = "anomalies"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_median: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_mad: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    series_name: Mapped[str] = mapped_column(String(128), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "severity IN ('warning','critical')",
            name="anomaly_severity_in_set",
        ),
        # Correlate() scans by time first, partitions by series.
        Index(
            "ix_anomalies_timestamp_series",
            "timestamp",
            "series_name",
        ),
    )

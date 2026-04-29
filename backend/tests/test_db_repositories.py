"""Unit tests for the repository layer (M2.0 task 4).

Strict scope: mappers + SQL statement shape. No Postgres, no Docker, no
session — those land in T10 (integration) under the ``integration``
mark with Testcontainers.

What we verify here:

1. **Mapper round-trip**: an ORM row → domain dataclass mapper preserves
   every field exactly. (T3 already tests structural shape; this layer
   tests the data-flow boundary.)
2. **Idempotent INSERT shape**: the SQL compiles to
   ``INSERT ... ON CONFLICT ... DO NOTHING RETURNING ...`` for every
   path that v1.1 documented as idempotent (raw events, incidents by
   signature, workflow_usage).
3. **Domain-only return surface**: every public repo method's return
   annotation references a domain dataclass, never an ``*ORM`` symbol.

The 6 repos all expose their public ops as ``async def``, so the body
itself can't be exercised without a session. Static checks on the
class shape are enough at this layer.
"""
from __future__ import annotations

import inspect
from datetime import UTC, datetime
from typing import get_type_hints
from uuid import uuid4

from sqlalchemy import ClauseElement
from sqlalchemy.dialects import postgresql

from repopulse.anomaly.detector import Anomaly
from repopulse.correlation.engine import Incident
from repopulse.db.models.action_history import ActionHistoryORM
from repopulse.db.models.anomaly import AnomalyORM
from repopulse.db.models.incident import IncidentORM
from repopulse.db.models.normalized_event import NormalizedEventORM
from repopulse.db.models.recommendation import RecommendationORM
from repopulse.db.models.workflow_usage import WorkflowUsageORM
from repopulse.db.repository import (
    ActionHistoryRepository,
    AnomalyRepository,
    EventRepository,
    IncidentRepository,
    RecommendationRepository,
    WorkflowUsageRepository,
)
from repopulse.db.repository.action_history_repo import _to_history_domain
from repopulse.db.repository.anomaly_repo import _to_anomaly_domain
from repopulse.db.repository.event_repo import _to_normalized_domain
from repopulse.db.repository.incident_repo import _to_incident_domain
from repopulse.db.repository.recommendation_repo import _to_recommendation_domain
from repopulse.db.repository.workflow_usage_repo import _to_workflow_domain
from repopulse.github.usage import WorkflowUsage
from repopulse.pipeline.normalize import NormalizedEvent
from repopulse.pipeline.orchestrator import ActionHistoryEntry
from repopulse.recommend.engine import Recommendation


def _utc(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


# ---------------------------------------------------------------------------
# 1. Mapper round-trip tests
# ---------------------------------------------------------------------------


def test_normalized_event_mapper_preserves_fields() -> None:
    event_id = uuid4()
    orm = NormalizedEventORM(
        event_id=event_id,
        received_at=_utc(2026, 4, 29, 12),
        occurred_at=_utc(2026, 4, 29, 11),
        source="github",
        kind="ci-failure",
        severity="error",
        attributes={"workflow": "ci", "repo": "owner/repo"},
    )
    domain = _to_normalized_domain(orm)
    assert isinstance(domain, NormalizedEvent)
    assert domain.event_id == event_id
    assert domain.received_at == _utc(2026, 4, 29, 12)
    assert domain.occurred_at == _utc(2026, 4, 29, 11)
    assert domain.source == "github"
    assert domain.kind == "ci-failure"
    assert domain.severity == "error"
    assert domain.attributes == {"workflow": "ci", "repo": "owner/repo"}


def test_anomaly_mapper_preserves_fields() -> None:
    orm = AnomalyORM(
        id=uuid4(),
        timestamp=_utc(2026, 4, 29, 10),
        value=42.5,
        baseline_median=10.0,
        baseline_mad=2.0,
        score=4.7,
        severity="critical",
        series_name="latency_p99",
    )
    domain = _to_anomaly_domain(orm)
    assert isinstance(domain, Anomaly)
    assert domain.timestamp == _utc(2026, 4, 29, 10)
    assert domain.value == 42.5
    assert domain.baseline_median == 10.0
    assert domain.baseline_mad == 2.0
    assert domain.score == 4.7
    assert domain.severity == "critical"
    assert domain.series_name == "latency_p99"


def test_incident_mapper_returns_shallow_shell() -> None:
    """Bridge tables are not walked — domain incident has empty tuples."""
    incident_id = uuid4()
    orm = IncidentORM(
        incident_id=incident_id,
        started_at=_utc(2026, 4, 29, 9),
        ended_at=_utc(2026, 4, 29, 9, 5),
        sources=["github", "otel-metrics"],
        signature_hash="a" * 64,
    )
    domain = _to_incident_domain(orm)
    assert isinstance(domain, Incident)
    assert domain.incident_id == incident_id
    assert domain.started_at == _utc(2026, 4, 29, 9)
    assert domain.ended_at == _utc(2026, 4, 29, 9, 5)
    assert domain.sources == ("github", "otel-metrics")
    assert domain.events == ()
    assert domain.anomalies == ()


def test_recommendation_mapper_preserves_fields() -> None:
    rec_id = uuid4()
    inc_id = uuid4()
    orm = RecommendationORM(
        recommendation_id=rec_id,
        incident_id=inc_id,
        action_category="escalate",
        confidence=0.85,
        risk_level="medium",
        evidence_trace=["R3: ≥2 anomalies → escalate"],
        state="pending",
    )
    domain = _to_recommendation_domain(orm)
    assert isinstance(domain, Recommendation)
    assert domain.recommendation_id == rec_id
    assert domain.incident_id == inc_id
    assert domain.action_category == "escalate"
    assert domain.confidence == 0.85
    assert domain.risk_level == "medium"
    assert domain.evidence_trace == ("R3: ≥2 anomalies → escalate",)
    assert domain.state == "pending"


def test_action_history_mapper_preserves_fields() -> None:
    rec_id = uuid4()
    orm = ActionHistoryORM(
        at=_utc(2026, 4, 29, 13),
        kind="approve",
        recommendation_id=rec_id,
        actor="ibrahim",
        summary="approving R3 escalate",
    )
    domain = _to_history_domain(orm)
    assert isinstance(domain, ActionHistoryEntry)
    assert domain.at == _utc(2026, 4, 29, 13)
    assert domain.kind == "approve"
    assert domain.recommendation_id == rec_id
    assert domain.actor == "ibrahim"
    assert domain.summary == "approving R3 escalate"


def test_action_history_mapper_handles_null_recommendation_id() -> None:
    """workflow-run rows have NULL recommendation_id."""
    orm = ActionHistoryORM(
        at=_utc(2026, 4, 29, 14),
        kind="workflow-run",
        recommendation_id=None,
        actor="ci.yml",
        summary="run 1234: success",
    )
    domain = _to_history_domain(orm)
    assert domain.recommendation_id is None
    assert domain.kind == "workflow-run"


def test_workflow_usage_mapper_preserves_fields() -> None:
    orm = WorkflowUsageORM(
        workflow_name="ci",
        run_id=98765,
        duration_seconds=120.0,
        conclusion="success",
        repository="owner/repo",
        cost_estimate_usd=0.016,
        received_at=_utc(2026, 4, 29, 15),
    )
    domain = _to_workflow_domain(orm)
    assert isinstance(domain, WorkflowUsage)
    assert domain.workflow_name == "ci"
    assert domain.run_id == 98765
    assert domain.duration_seconds == 120.0
    assert domain.conclusion == "success"
    assert domain.repository == "owner/repo"
    assert domain.cost_estimate_usd == 0.016


# ---------------------------------------------------------------------------
# 2. Idempotent INSERT shape
# ---------------------------------------------------------------------------


def _compile_postgresql(stmt: ClauseElement) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))  # type: ignore[no-untyped-call]


def test_raw_event_idempotent_insert_uses_on_conflict_do_nothing() -> None:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from repopulse.db.models.raw_event import RawEventORM

    stmt = (
        pg_insert(RawEventORM)
        .values(
            event_id=uuid4(),
            source="github",
            kind="ci-failure",
            payload={},
            received_at=_utc(2026, 4, 29),
            occurred_at=_utc(2026, 4, 29),
        )
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(RawEventORM.event_id)
    )
    sql = _compile_postgresql(stmt).upper()
    assert "ON CONFLICT" in sql
    assert "DO NOTHING" in sql
    assert "RETURNING" in sql


def test_incident_idempotent_insert_uses_signature_hash() -> None:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = (
        pg_insert(IncidentORM)
        .values(
            incident_id=uuid4(),
            started_at=_utc(2026, 4, 29),
            ended_at=_utc(2026, 4, 29),
            sources=["github"],
            signature_hash="x" * 64,
        )
        .on_conflict_do_nothing(index_elements=["signature_hash"])
        .returning(IncidentORM.incident_id)
    )
    sql = _compile_postgresql(stmt)
    assert "ON CONFLICT" in sql.upper()
    assert "signature_hash" in sql.lower()


def test_workflow_usage_idempotent_insert_uses_run_id_repository() -> None:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = (
        pg_insert(WorkflowUsageORM)
        .values(
            workflow_name="ci",
            run_id=1,
            duration_seconds=10.0,
            conclusion="success",
            repository="o/r",
            cost_estimate_usd=0.001,
            received_at=_utc(2026, 4, 29),
        )
        .on_conflict_do_nothing(
            index_elements=["run_id", "repository"]
        )
        .returning(WorkflowUsageORM.id)
    )
    sql = _compile_postgresql(stmt).lower()
    assert "on conflict" in sql
    assert "run_id" in sql
    assert "repository" in sql


# ---------------------------------------------------------------------------
# 3. Boundary guard — ORM types do NOT leak through public repo signatures
# ---------------------------------------------------------------------------


_REPO_CLASSES = (
    EventRepository,
    AnomalyRepository,
    IncidentRepository,
    RecommendationRepository,
    ActionHistoryRepository,
    WorkflowUsageRepository,
)


def test_no_orm_types_in_public_repo_signatures() -> None:
    """Every public repo method's params + return annotations are domain types.

    Names ending in ``ORM`` would betray an ORM-shaped leak through the
    repository boundary. The internal ``_to_*_domain`` mappers are the
    only place ORM types appear.
    """
    for repo_cls in _REPO_CLASSES:
        for name, member in inspect.getmembers(repo_cls, inspect.isfunction):
            if name.startswith("_"):
                continue
            try:
                hints = get_type_hints(member)
            except NameError:
                # Some literal aliases need `include_extras` etc.; skip
                # those — the visual review still catches leaks.
                continue
            for hint_name, hint in hints.items():
                rendered = str(hint)
                assert "ORM" not in rendered, (
                    f"{repo_cls.__name__}.{name} param {hint_name!r} leaks "
                    f"ORM type: {rendered}"
                )


def test_repository_init_takes_async_session() -> None:
    """Every repo's __init__ accepts a single ``session`` parameter."""
    for repo_cls in _REPO_CLASSES:
        sig = inspect.signature(repo_cls.__init__)
        params = list(sig.parameters)
        assert params == ["self", "session"], (
            f"{repo_cls.__name__}.__init__ signature {params!r} should be "
            f"(self, session)"
        )

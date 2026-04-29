"""Repository layer for the persistent storage backend (M2.0 task 4).

Each repository is a thin async class scoped to one aggregate. Repos
**return domain dataclasses**, never ORM rows — the boundary between the
persistence layer and the rest of the codebase is enforced here.

Per the M2.0 plan:

- Repos never call other repos. The orchestrator (T5) or a future service
  layer composes them.
- All operations take an :class:`sqlalchemy.ext.asyncio.AsyncSession`.
  Transaction boundaries are owned by the caller. A repo never commits
  on its own.
- Idempotent inserts go through PostgreSQL's
  ``INSERT ... ON CONFLICT DO NOTHING RETURNING`` pattern, never through
  read-then-write races.
"""
from repopulse.db.repository.action_history_repo import ActionHistoryRepository
from repopulse.db.repository.anomaly_repo import AnomalyRepository
from repopulse.db.repository.event_repo import EventRepository
from repopulse.db.repository.incident_repo import IncidentRepository
from repopulse.db.repository.recommendation_repo import RecommendationRepository
from repopulse.db.repository.workflow_usage_repo import WorkflowUsageRepository

__all__ = [
    "ActionHistoryRepository",
    "AnomalyRepository",
    "EventRepository",
    "IncidentRepository",
    "RecommendationRepository",
    "WorkflowUsageRepository",
]

"""ORM model registry for the storage layer (M2.0).

Importing this package side-effect-registers every model on the shared
:data:`repopulse.db.base.metadata`. Alembic's ``env.py`` and the test
``Base.metadata.create_all(engine)`` path both rely on that registration,
so any new model file must be re-exported here even if no caller imports
the symbol directly.

Bridge tables (``incident_events``, ``incident_anomalies``) are plain
:class:`Table` objects defined in :mod:`.incident`; importing that module
registers them too.
"""
from repopulse.db.models.action_history import (
    ACTION_KIND_VALUES,
    ActionHistoryORM,
)
from repopulse.db.models.anomaly import (
    ANOMALY_SEVERITY_VALUES,
    AnomalyORM,
)
from repopulse.db.models.incident import (
    IncidentORM,
    incident_anomalies,
    incident_events,
)
from repopulse.db.models.normalized_event import (
    SEVERITY_VALUES,
    NormalizedEventORM,
)
from repopulse.db.models.raw_event import RawEventORM
from repopulse.db.models.recommendation import (
    ACTION_CATEGORY_VALUES,
    RISK_LEVEL_VALUES,
    STATE_VALUES,
    RecommendationORM,
)
from repopulse.db.models.recommendation_transition import (
    RecommendationTransitionORM,
)
from repopulse.db.models.workflow_usage import WorkflowUsageORM

__all__ = [
    # Models
    "RawEventORM",
    "NormalizedEventORM",
    "AnomalyORM",
    "IncidentORM",
    "RecommendationORM",
    "RecommendationTransitionORM",
    "ActionHistoryORM",
    "WorkflowUsageORM",
    # Bridge tables
    "incident_events",
    "incident_anomalies",
    # Allowed-value constants
    "SEVERITY_VALUES",
    "ANOMALY_SEVERITY_VALUES",
    "ACTION_CATEGORY_VALUES",
    "RISK_LEVEL_VALUES",
    "STATE_VALUES",
    "ACTION_KIND_VALUES",
]

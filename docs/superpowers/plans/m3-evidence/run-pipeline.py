"""M3 evidence: drive synthetic events through the full pipeline and dump the
recommendations JSON. Mirrors the API's internal flow (orchestrator.ingest -->
evaluate --> latest_recommendations) so the captured JSON matches what
GET /api/v1/recommendations would return after evaluate() runs."""
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.pipeline.orchestrator import PipelineOrchestrator

T0 = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)
orch = PipelineOrchestrator()

# 5 GitHub push events
for i in range(5):
    env = EventEnvelope.model_validate(
        {"event_id": uuid4(), "source": "github", "kind": "push",
         "payload": {"commit": i}}
    )
    orch.ingest(env, received_at=T0 + timedelta(seconds=i * 10))

# 1 otel-logs error event
err_env = EventEnvelope.model_validate(
    {"event_id": uuid4(), "source": "otel-logs", "kind": "error",
     "payload": {"severity": "error", "message": "db conn refused"}}
)
orch.ingest(err_env, received_at=T0 + timedelta(seconds=55))

# 3 anomalies (1 critical, 2 warning) within the same window
orch.record_anomalies([
    Anomaly(timestamp=T0 + timedelta(seconds=20), value=300.0,
            baseline_median=10.0, baseline_mad=1.0, score=20.0,
            severity="critical", series_name="otel-metrics"),
    Anomaly(timestamp=T0 + timedelta(seconds=40), value=100.0,
            baseline_median=10.0, baseline_mad=1.0, score=5.5,
            severity="warning", series_name="otel-metrics"),
    Anomaly(timestamp=T0 + timedelta(seconds=60), value=110.0,
            baseline_median=10.0, baseline_mad=1.0, score=5.8,
            severity="warning", series_name="otel-metrics"),
])

new_recs = orch.evaluate(window_seconds=300.0)

print("snapshot:", json.dumps(orch.snapshot()))
print(f"new recommendations: {len(new_recs)}")

# Serialize like the API does
out = {
    "snapshot": orch.snapshot(),
    "recommendations": [
        {
            "recommendation_id": str(r.recommendation_id),
            "incident_id": str(r.incident_id),
            "action_category": r.action_category,
            "confidence": r.confidence,
            "risk_level": r.risk_level,
            "evidence_trace": list(r.evidence_trace),
        }
        for r in new_recs
    ],
}
print(json.dumps(out, indent=2))

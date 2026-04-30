"""M3 evidence: drive synthetic events through the full pipeline and dump the
recommendations JSON. Mirrors the API's internal flow (orchestrator.ingest -->
evaluate --> latest_recommendations) so the captured JSON matches what
GET /api/v1/recommendations would return after evaluate() runs."""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.testing import make_inmem_orchestrator

T0 = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


async def _main() -> None:
    orch, _ = make_inmem_orchestrator()

    for i in range(5):
        env = EventEnvelope.model_validate(
            {
                "event_id": uuid4(),
                "source": "github",
                "kind": "push",
                "payload": {"commit": i},
            }
        )
        await orch.ingest(env, received_at=T0 + timedelta(seconds=i * 10))

    err_env = EventEnvelope.model_validate(
        {
            "event_id": uuid4(),
            "source": "otel-logs",
            "kind": "error",
            "payload": {"severity": "error", "message": "db conn refused"},
        }
    )
    await orch.ingest(err_env, received_at=T0 + timedelta(seconds=55))

    await orch.record_anomalies(
        [
            Anomaly(
                timestamp=T0 + timedelta(seconds=20),
                value=300.0,
                baseline_median=10.0,
                baseline_mad=1.0,
                score=20.0,
                severity="critical",
                series_name="otel-metrics",
            ),
            Anomaly(
                timestamp=T0 + timedelta(seconds=40),
                value=100.0,
                baseline_median=10.0,
                baseline_mad=1.0,
                score=5.5,
                severity="warning",
                series_name="otel-metrics",
            ),
            Anomaly(
                timestamp=T0 + timedelta(seconds=60),
                value=110.0,
                baseline_median=10.0,
                baseline_mad=1.0,
                score=5.8,
                severity="warning",
                series_name="otel-metrics",
            ),
        ]
    )

    new_recs = await orch.evaluate(window_seconds=300.0)
    snap = await orch.snapshot()

    print("snapshot:", json.dumps(snap))
    print(f"new recommendations: {len(new_recs)}")

    out = {
        "snapshot": snap,
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


if __name__ == "__main__":
    asyncio.run(_main())

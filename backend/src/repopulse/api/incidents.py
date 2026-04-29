"""GET /api/v1/incidents — read-only view of orchestrator incidents.

Used by the operator dashboard's incidents-timeline page. Returns the
most-recent ``limit`` incidents, newest-first. Requires pipeline API auth
(v1.1).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from repopulse.api.pipeline_auth import require_pipeline_api_key
from repopulse.config import Settings

router = APIRouter(prefix="/api/v1", tags=["incidents"])


@router.get("/incidents")
async def list_incidents(
    request: Request,
    _settings: Annotated[Settings, Depends(require_pipeline_api_key)],
    limit: int = Query(default=50, ge=0, le=200),
) -> dict[str, object]:
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        return {"incidents": [], "count": 0}
    triples = await orchestrator.latest_incidents_with_counts(limit=limit)
    out = [
        {
            "incident_id": str(inc.incident_id),
            "started_at": inc.started_at.isoformat(),
            "ended_at": inc.ended_at.isoformat(),
            "sources": sorted(inc.sources),
            "anomaly_count": anomaly_count,
            "event_count": event_count,
        }
        for inc, anomaly_count, event_count in triples
    ]
    return {"incidents": out, "count": len(out)}

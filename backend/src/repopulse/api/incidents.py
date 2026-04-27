"""GET /api/v1/incidents — read-only view of orchestrator incidents.

Used by the operator dashboard's incidents-timeline page. Returns the
most-recent ``limit`` incidents, newest-first.
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/api/v1", tags=["incidents"])


@router.get("/incidents")
def list_incidents(
    request: Request,
    limit: int = Query(default=50, ge=0, le=200),
) -> dict[str, object]:
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        return {"incidents": [], "count": 0}
    incidents = orchestrator.latest_incidents(limit=limit)
    out = [
        {
            "incident_id": str(inc.incident_id),
            "started_at": inc.started_at.isoformat(),
            "ended_at": inc.ended_at.isoformat(),
            "sources": sorted(inc.sources),
            "anomaly_count": len(inc.anomalies),
            "event_count": len(inc.events),
        }
        for inc in incidents
    ]
    return {"incidents": out, "count": len(out)}

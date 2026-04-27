"""GET /api/v1/actions — operator action history (M4).

Returns the orchestrator's bounded action-history deque, newest-first.
Includes operator approvals/rejections, R1 auto-observe entries, and
agentic-workflow run entries (M5 source) once those are wired in.
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/api/v1", tags=["actions"])


@router.get("/actions")
def list_actions(
    request: Request,
    limit: int = Query(default=50, ge=0, le=200),
) -> dict[str, object]:
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        return {"actions": [], "count": 0}
    entries = orchestrator.latest_actions(limit=limit)
    out = [
        {
            "at": entry.at.isoformat(),
            "kind": entry.kind,
            "recommendation_id": (
                str(entry.recommendation_id)
                if entry.recommendation_id is not None
                else None
            ),
            "actor": entry.actor,
            "summary": entry.summary,
        }
        for entry in entries
    ]
    return {"actions": out, "count": len(out)}

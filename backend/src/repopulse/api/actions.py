"""GET /api/v1/actions — operator action history (M4).

Returns the orchestrator's bounded action-history deque, newest-first.
Includes operator approvals/rejections, R1 auto-observe entries, and
agentic-workflow run entries (M5 source) once those are wired in.
Requires pipeline API auth (v1.1).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from repopulse.api.pipeline_auth import require_pipeline_api_key
from repopulse.config import Settings

router = APIRouter(prefix="/api/v1", tags=["actions"])


@router.get("/actions")
def list_actions(
    request: Request,
    _settings: Annotated[Settings, Depends(require_pipeline_api_key)],
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

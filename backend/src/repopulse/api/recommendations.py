"""Recommendations API.

Returns the latest recommendations from the in-memory orchestrator on
``app.state.orchestrator``. The orchestrator is created (or supplied)
in :func:`repopulse.main.create_app`.
"""
from __future__ import annotations

from typing import TypedDict

from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/api/v1", tags=["recommendations"])


class RecommendationOut(TypedDict):
    recommendation_id: str
    incident_id: str
    action_category: str
    confidence: float
    risk_level: str
    evidence_trace: list[str]


class RecommendationsResponse(TypedDict):
    recommendations: list[RecommendationOut]
    count: int


@router.get("/recommendations")
def list_recommendations(
    request: Request,
    limit: int = Query(default=10, ge=0, le=100),
) -> RecommendationsResponse:
    orchestrator = request.app.state.orchestrator
    recs = orchestrator.latest_recommendations(limit=limit)
    serialized: list[RecommendationOut] = [
        {
            "recommendation_id": str(r.recommendation_id),
            "incident_id": str(r.incident_id),
            "action_category": r.action_category,
            "confidence": r.confidence,
            "risk_level": r.risk_level,
            "evidence_trace": list(r.evidence_trace),
        }
        for r in recs
    ]
    return {"recommendations": serialized, "count": len(serialized)}

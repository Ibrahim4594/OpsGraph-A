"""Recommendations API.

GET /api/v1/recommendations            — list latest, with state overlay
POST /api/v1/recommendations/{id}/approve  — operator approval (M4)
POST /api/v1/recommendations/{id}/reject   — operator rejection (M4)

The orchestrator on ``app.state.orchestrator`` owns the bounded
recommendations deque and the state-overlay dict.
"""
from __future__ import annotations

from typing import TypedDict
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1", tags=["recommendations"])


class RecommendationOut(TypedDict):
    recommendation_id: str
    incident_id: str
    action_category: str
    confidence: float
    risk_level: str
    evidence_trace: list[str]
    state: str


class RecommendationsResponse(TypedDict):
    recommendations: list[RecommendationOut]
    count: int


class _ApproveBody(BaseModel):
    operator: str = Field(min_length=1, max_length=128)


class _RejectBody(BaseModel):
    operator: str = Field(min_length=1, max_length=128)
    reason: str | None = Field(default=None, max_length=512)


def _serialize(rec: object) -> RecommendationOut:
    return {
        "recommendation_id": str(rec.recommendation_id),  # type: ignore[attr-defined]
        "incident_id": str(rec.incident_id),  # type: ignore[attr-defined]
        "action_category": rec.action_category,  # type: ignore[attr-defined]
        "confidence": rec.confidence,  # type: ignore[attr-defined]
        "risk_level": rec.risk_level,  # type: ignore[attr-defined]
        "evidence_trace": list(rec.evidence_trace),  # type: ignore[attr-defined]
        "state": rec.state,  # type: ignore[attr-defined]
    }


@router.get("/recommendations")
def list_recommendations(
    request: Request,
    limit: int = Query(default=10, ge=0, le=100),
) -> RecommendationsResponse:
    orchestrator = request.app.state.orchestrator
    recs = orchestrator.latest_recommendations(limit=limit)
    serialized = [_serialize(rec) for rec in recs]
    return {"recommendations": serialized, "count": len(serialized)}


@router.post("/recommendations/{rec_id}/approve")
def approve_recommendation(
    rec_id: UUID,
    body: _ApproveBody,
    request: Request,
) -> dict[str, object]:
    orchestrator = request.app.state.orchestrator
    try:
        rec = orchestrator.transition_recommendation(
            rec_id, to_state="approved", actor=body.operator
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="recommendation not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "recommendation_id": str(rec_id),
        "state": rec.state,
        "actor": body.operator,
    }


@router.post("/recommendations/{rec_id}/reject")
def reject_recommendation(
    rec_id: UUID,
    body: _RejectBody,
    request: Request,
) -> dict[str, object]:
    orchestrator = request.app.state.orchestrator
    try:
        rec = orchestrator.transition_recommendation(
            rec_id,
            to_state="rejected",
            actor=body.operator,
            reason=body.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="recommendation not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "recommendation_id": str(rec_id),
        "state": rec.state,
        "actor": body.operator,
    }

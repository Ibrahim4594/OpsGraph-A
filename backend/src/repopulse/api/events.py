"""Events ingest endpoint.

POST /api/v1/events accepts a canonical event envelope and returns 202
Accepted on success. Validation failures return 422 (FastAPI default for
pydantic errors). The ``simulate_error`` flag exists so the synthetic
load generator (and the SLO module) can exercise the error path
deterministically — production traffic must always set it false.
"""
from __future__ import annotations

from typing import Literal, TypedDict
from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1", tags=["events"])


class EventEnvelope(BaseModel):
    """Canonical inbound event payload."""

    event_id: UUID
    source: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    payload: dict[str, object] = Field(default_factory=dict)
    simulate_error: bool = False


class IngestResponse(TypedDict):
    accepted: Literal[True]
    event_id: str


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
def ingest_event(envelope: EventEnvelope) -> IngestResponse:
    if envelope.simulate_error:
        raise RuntimeError("simulated ingest failure")
    return {"accepted": True, "event_id": str(envelope.event_id)}

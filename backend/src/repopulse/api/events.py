"""Events ingest endpoint.

POST /api/v1/events accepts a canonical event envelope and returns 202
Accepted on success. Requires ``Authorization: Bearer
<REPOPULSE_API_SHARED_SECRET>`` (v1.1). Validation failures return 422.

The ``simulate_error`` flag is **disabled by default**; set
``REPOPULSE_ALLOW_SIMULATE_ERROR=true`` for synthetic load / tests only.

On a successful ingest the envelope is forwarded to the in-memory
``PipelineOrchestrator`` (``app.state.orchestrator``) and a fresh
``evaluate()`` cycle is run so that ``GET /api/v1/recommendations``
reflects the new event without a separate trigger call.
"""
from __future__ import annotations

import json
from typing import Annotated, Literal, TypedDict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from repopulse.api.pipeline_auth import require_pipeline_api_key
from repopulse.config import Settings

router = APIRouter(prefix="/api/v1", tags=["events"])

_MAX_PAYLOAD_BYTES = 256 * 1024


class EventEnvelope(BaseModel):
    """Canonical inbound event payload.

    ``extra="forbid"`` (v1.1 post-review I2) — silently dropping unknown
    fields hid the operator-identity drift the audit story relies on; loud
    rejection at the boundary is the right default.
    """

    model_config = {"extra": "forbid"}

    event_id: UUID
    source: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    payload: dict[str, object] = Field(default_factory=dict)
    simulate_error: bool = False

    @field_validator("payload")
    @classmethod
    def _payload_size_cap(cls, v: dict[str, object]) -> dict[str, object]:
        raw = json.dumps(v, separators=(",", ":"), default=str).encode("utf-8")
        if len(raw) > _MAX_PAYLOAD_BYTES:
            raise ValueError(
                f"payload JSON must be <= {_MAX_PAYLOAD_BYTES} bytes when serialized"
            )
        return v


class IngestResponse(TypedDict):
    accepted: Literal[True]
    event_id: str


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
def ingest_event(
    envelope: EventEnvelope,
    request: Request,
    settings: Annotated[Settings, Depends(require_pipeline_api_key)],
) -> IngestResponse:
    if envelope.simulate_error:
        if not settings.allow_simulate_error:
            raise HTTPException(
                status_code=403,
                detail="simulate_error is disabled; set REPOPULSE_ALLOW_SIMULATE_ERROR=true",
            )
        raise RuntimeError("simulated ingest failure")
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is not None:
        orchestrator.ingest(envelope)
        orchestrator.evaluate()
    return {"accepted": True, "event_id": str(envelope.event_id)}

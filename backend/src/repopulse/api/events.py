"""Events ingest endpoint.

POST /api/v1/events accepts a canonical event envelope and returns 202
Accepted on success. Requires ``Authorization: Bearer
<REPOPULSE_API_SHARED_SECRET>`` (v1.1). Validation failures return 422.

The ``simulate_error`` flag is **disabled by default**; set
``REPOPULSE_ALLOW_SIMULATE_ERROR=true`` for synthetic load / tests only.

Idempotency contract (T6, v2.0)
-------------------------------

POST is **idempotent on ``event_id``**. The operator may safely retry
this endpoint — for example, after a network blip or load-balancer
reset — without producing duplicate events, anomalies, incidents, or
recommendations:

- **Fresh ``event_id``**: 202 with body
  ``{"accepted": true, "event_id": "<uuid>", "duplicate": false}``.
  The envelope is persisted, normalised, and a fresh ``evaluate()``
  cycle is run so ``GET /api/v1/recommendations`` reflects the new event.
- **Duplicate ``event_id`` (already ingested)**: still 202 with body
  ``{"accepted": true, "event_id": "<uuid>", "duplicate": true}``.
  No persistence side effects; ``evaluate()`` is skipped.

We deliberately do **not** return 409 on duplicates: 409 would force
clients to special-case a benign retry, when the entire point of an
``event_id`` is to make retries safe. See
``docs/ingest-idempotency.md`` for the full design rationale.
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
    duplicate: bool


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(
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
    duplicate = False
    if orchestrator is not None:
        normalized = await orchestrator.ingest(envelope)
        if normalized is None:
            # event_id has already been ingested. The PK on raw_events is
            # the idempotency anchor — see ``docs/ingest-idempotency.md``.
            duplicate = True
        else:
            await orchestrator.evaluate()
    return {
        "accepted": True,
        "event_id": str(envelope.event_id),
        "duplicate": duplicate,
    }

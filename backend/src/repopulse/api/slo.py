"""GET /api/v1/slo — service-level state derived from the event log.

Counts the orchestrator's recorded events, classifies error events
(``severity in ('error', 'critical')`` or ``kind == 'error-log'``), and
returns availability + error budget + burn rate. Reuses the pure
functions in :mod:`repopulse.slo`. Requires pipeline API auth (v1.1).
"""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request

from repopulse.api.pipeline_auth import require_pipeline_api_key
from repopulse.config import Settings
from repopulse.slo import (
    SLO,
    availability_sli,
    burn_rate,
    error_budget,
    is_fast_burn,
    is_slow_burn,
)

router = APIRouter(prefix="/api/v1", tags=["slo"])

BurnBand = Literal["ok", "slow", "fast"]


def _classify_event(kind: str, severity: str) -> bool:
    """Return True iff the event counts as an SLO error."""
    if kind == "error-log":
        return True
    return severity in ("error", "critical")


def _band(burn: float, *, over_budget: bool) -> BurnBand:
    """Map the burn rate to a dashboard-visible band.

    - ``fast``: burn >= 14.4 (page-worthy per SRE multi-window alert).
    - ``slow``: 6 <= burn < 14.4 OR over-budget at any positive burn (so
      the operator sees over-budget on the dashboard even before the
      page-worthy threshold).
    - ``ok``: within target AND below the slow-burn threshold.
    """
    if is_fast_burn(burn=burn):
        return "fast"
    if is_slow_burn(burn=burn) or over_budget:
        return "slow"
    return "ok"


@router.get("/slo")
async def get_slo(
    request: Request,
    _settings: Annotated[Settings, Depends(require_pipeline_api_key)],
    target: float = Query(default=0.99, ge=0.0, le=1.0),
) -> dict[str, object]:
    orchestrator = getattr(request.app.state, "orchestrator", None)
    events = await orchestrator.iter_events() if orchestrator is not None else []
    total = len(events)
    errors = sum(
        1 for ev in events if _classify_event(ev.kind, ev.severity)
    )
    successes = total - errors
    availability = availability_sli(success_count=successes, total_count=total)

    slo = SLO(target=target)
    actual_error_rate = 0.0 if total == 0 else errors / total
    burn = (
        0.0
        if total == 0
        else burn_rate(actual_error_rate=actual_error_rate, slo=slo)
    )
    over_budget = total > 0 and availability < target
    band: BurnBand = "ok" if not over_budget else _band(burn, over_budget=True)

    return {
        "service": "RepoPulse",
        "total_events": total,
        "error_events": errors,
        "availability": availability,
        "target": target,
        "error_budget_remaining": error_budget(slo) - actual_error_rate,
        "burn_rate": burn,
        "burn_band": band,
    }

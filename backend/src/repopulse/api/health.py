"""Health endpoint."""
from typing import Literal, TypedDict

from fastapi import APIRouter

from repopulse import __version__
from repopulse.config import Settings

router = APIRouter()


class HealthPayload(TypedDict):
    status: Literal["ok"]
    service: str
    environment: str
    version: str
    agentic_enabled: bool


@router.get("/healthz")
def healthz() -> HealthPayload:
    """Liveness probe — always returns ok if the app is up.

    ``agentic_enabled`` reflects ``REPOPULSE_AGENTIC_ENABLED`` at request
    time so the operator dashboard's status bar can surface the kill-switch
    state without holding a separate signal channel. Reading via
    ``Settings()`` keeps the M5 ADR-003 "milliseconds to take effect"
    guarantee — env-var flips show up on the next /healthz poll.
    """
    settings = Settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
        "version": __version__,
        "agentic_enabled": settings.agentic_enabled,
    }

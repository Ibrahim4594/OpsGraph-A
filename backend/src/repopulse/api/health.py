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


@router.get("/healthz")
def healthz() -> HealthPayload:
    """Liveness probe — always returns ok if the app is up."""
    settings = Settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
        "version": __version__,
    }

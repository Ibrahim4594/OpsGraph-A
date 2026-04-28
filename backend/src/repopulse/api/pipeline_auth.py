"""Bearer authentication for operator pipeline HTTP APIs (v1.1).

Uses ``Authorization: Bearer <REPOPULSE_API_SHARED_SECRET>``, separate from
``REPOPULSE_AGENTIC_SHARED_SECRET`` (GitHub agentic workflows, M5).

If ``REPOPULSE_API_SHARED_SECRET`` is unset, protected routes return **503**
(fail closed).
"""
from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from repopulse.config import Settings


def get_settings() -> Settings:
    """Fresh ``Settings`` per request (env changes honored without restart)."""
    return Settings()


def require_pipeline_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> Settings:
    """Validate pipeline API bearer token; return settings on success."""
    expected = settings.api_shared_secret
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="pipeline API shared secret not configured",
        )
    token = (authorization or "").removeprefix("Bearer ").strip()
    exp_b = expected.encode("utf-8")
    tok_b = token.encode("utf-8")
    try:
        ok = hmac.compare_digest(tok_b, exp_b)
    except (TypeError, ValueError):
        ok = False
    if not ok:
        raise HTTPException(status_code=401, detail="invalid pipeline API token")
    return settings

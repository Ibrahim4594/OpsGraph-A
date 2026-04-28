"""CORS guards (v1.1 post-review C1).

CORS with ``allow_credentials=True`` and a wildcard origin is unsafe per
spec; Starlette's CORSMiddleware reflects the request ``Origin`` back,
which together with the documented ``NEXT_PUBLIC_API_SHARED_SECRET``
browser-bundle exposure would let any site make authenticated requests.
``create_app`` must refuse this combination at startup.
"""
from __future__ import annotations

import pytest

from repopulse.main import create_app


def test_create_app_refuses_wildcard_cors_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPOPULSE_CORS_ORIGINS", "*")
    with pytest.raises(ValueError, match="wildcard"):
        create_app()


def test_create_app_refuses_wildcard_within_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "REPOPULSE_CORS_ORIGINS", "http://localhost:3000,*"
    )
    with pytest.raises(ValueError, match="wildcard"):
        create_app()


def test_create_app_accepts_explicit_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "REPOPULSE_CORS_ORIGINS",
        "http://127.0.0.1:3000,http://localhost:3000",
    )
    app = create_app()
    # Should boot cleanly with both listed origins.
    assert app.title == "RepoPulse AIOps"


def test_create_app_no_cors_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REPOPULSE_CORS_ORIGINS", raising=False)
    app = create_app()
    assert app.title == "RepoPulse AIOps"

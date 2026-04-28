"""Application settings loaded from environment."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """RepoPulse runtime settings.

    Env vars use the prefix ``REPOPULSE_`` (e.g. ``REPOPULSE_LOG_LEVEL=DEBUG``).
    """

    model_config = SettingsConfigDict(
        env_prefix="REPOPULSE_",
        env_file=".env",
        extra="ignore",
    )

    app_name: str = "RepoPulse"
    environment: str = "development"
    log_level: str = "INFO"
    agentic_enabled: bool = True
    agentic_shared_secret: str | None = None
    #: Bearer token for ``/api/v1/events``, recommendations, incidents, actions,
    #: and SLO read APIs. Required in production; unset → 503 on those routes.
    api_shared_secret: str | None = None
    #: Audit ``actor`` recorded for approve/reject when using the shared API key
    #: (never taken from untrusted request body).
    api_operator_actor: str = "authenticated-api"
    #: Allow ``simulate_error`` on ``POST /api/v1/events`` (dev/load-test only).
    allow_simulate_error: bool = False
    #: Comma-separated browser origins for CORS (e.g. ``http://127.0.0.1:3000``).
    #: Empty → no CORS middleware (same-origin or reverse-proxy only).
    cors_origins: str = ""
    #: Max ``Content-Length`` in bytes accepted on any HTTP request body.
    #: Larger requests are rejected with 413 *before* Starlette parses them.
    #: Default 384 KiB = 256 KiB payload cap + envelope/headers overhead.
    max_request_bytes: int = 384 * 1024
    #: Database URL for the storage layer (M2.0+).
    #:
    #: Format: ``postgresql+psycopg://<user>:<pass>@<host>:<port>/<db>``.
    #: **Optional** at the Settings level — unit tests and the v1.1 in-memory
    #: orchestrator do not require a database. Code paths that need the DB
    #: (Alembic, repositories, the M2.0+ orchestrator facade) raise
    #: ``RuntimeError`` if this is unset when they are invoked.
    database_url: str | None = None
    #: Connection-pool size for the async engine. Defaults are tuned for a
    #: single uvicorn worker; revisit when M4.0 multi-worker compose lands.
    database_pool_size: int = 5
    database_pool_max_overflow: int = 10

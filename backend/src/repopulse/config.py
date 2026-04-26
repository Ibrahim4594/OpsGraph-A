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

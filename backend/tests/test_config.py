"""Settings model contract."""
from repopulse.config import Settings


def test_settings_default_app_name() -> None:
    s = Settings()
    assert s.app_name == "RepoPulse"


def test_settings_env_override(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("REPOPULSE_APP_NAME", "TestApp")
    monkeypatch.setenv("REPOPULSE_LOG_LEVEL", "DEBUG")
    s = Settings()
    assert s.app_name == "TestApp"
    assert s.log_level == "DEBUG"


def test_settings_default_log_level() -> None:
    s = Settings()
    assert s.log_level == "INFO"


def test_settings_default_environment() -> None:
    s = Settings()
    assert s.environment == "development"

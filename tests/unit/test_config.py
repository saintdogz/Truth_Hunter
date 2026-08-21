"""Configuration validation tests."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_trusted_hosts_are_parsed() -> None:
    settings = Settings(app_env="test", app_trusted_hosts="localhost, example.test ")

    assert settings.trusted_hosts == ["localhost", "example.test"]


def test_non_postgresql_database_is_rejected() -> None:
    with pytest.raises(ValidationError, match="PostgreSQL"):
        Settings(app_env="test", database_url="sqlite:///test.db")


def test_production_rejects_placeholder_secret() -> None:
    with pytest.raises(ValidationError, match="APP_SECRET"):
        Settings(app_env="production", app_secret="development-only-change-me")


def test_production_accepts_replaced_secret() -> None:
    settings = Settings(app_env="production", app_secret="a-unique-production-value")

    assert settings.app_env == "production"


def test_phase_two_resource_limits_are_validated() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="test", source_useful_limit=16)


def test_production_rejects_placeholder_ai_key() -> None:
    with pytest.raises(ValidationError, match="AI_API_KEY"):
        Settings(
            app_env="production",
            app_secret="a-unique-production-value",
            ai_api_key="development-only-change-me",
        )

"""Configuration validation tests."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.main import validate_runtime_adapters


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


def test_production_rejects_development_email_adapter() -> None:
    settings = Settings(
        app_env="production",
        app_secret="a-unique-production-value",
        email_delivery_mode="development",
    )

    with pytest.raises(ValueError, match="Production email"):
        validate_runtime_adapters(settings)


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


def test_empty_optional_ai_key_is_unset() -> None:
    settings = Settings(app_env="test", ai_api_key="")

    assert settings.ai_api_key is None


def test_deepseek_provider_is_accepted() -> None:
    settings = Settings(
        app_env="test",
        ai_provider="deepseek",
        ai_api_key="test-key",
        ai_model="deepseek-v4-flash",
    )

    assert settings.ai_provider == "deepseek"
    assert settings.ai_model == "deepseek-v4-flash"


def test_groq_with_deepseek_fallback_is_accepted() -> None:
    settings = Settings(
        app_env="test",
        ai_provider="groq",
        ai_api_key="groq-test-key",
        ai_model="openai/gpt-oss-120b",
        ai_fallback_provider="deepseek",
        ai_fallback_api_key="deepseek-test-key",
        ai_fallback_model="deepseek-v4-flash",
    )

    assert settings.ai_provider == "groq"
    assert settings.ai_fallback_provider == "deepseek"


def test_partial_fallback_configuration_is_rejected() -> None:
    with pytest.raises(ValidationError, match="provided together"):
        Settings(app_env="test", ai_fallback_provider="deepseek")


def test_empty_compose_fallback_values_are_unset() -> None:
    settings = Settings(
        app_env="test",
        ai_fallback_provider="",
        ai_fallback_api_key="",
        ai_fallback_model="",
    )

    assert settings.ai_fallback_provider is None

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


def test_image_resource_limits_are_validated() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="test", image_upload_max_bytes=20_000_000)
    with pytest.raises(ValidationError):
        Settings(app_env="test", image_upload_max_pixels=50_000_000)


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


def test_empty_optional_brave_search_key_is_unset() -> None:
    settings = Settings(app_env="test", brave_search_api_key="")

    assert settings.brave_search_api_key is None


def test_optional_support_url_can_be_configured_or_hidden() -> None:
    assert Settings(app_env="test", support_url="").support_url is None
    settings = Settings(app_env="test", support_url="https://support.example.com/truth-hunter")
    assert str(settings.support_url) == "https://support.example.com/truth-hunter"


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


def test_admin_email_allowlist_is_normalized() -> None:
    settings = Settings(
        app_env="test",
        admin_emails=" Owner@Example.com,second@example.com, ",
    )

    assert settings.admin_email_allowlist == {"owner@example.com", "second@example.com"}


def test_turnstile_requires_a_complete_key_pair() -> None:
    with pytest.raises(ValidationError, match="required together"):
        Settings(app_env="test", turnstile_site_key="site-only")


def test_turnstile_test_keys_are_rejected_in_production() -> None:
    with pytest.raises(ValidationError, match="test keys"):
        Settings(
            app_env="production",
            app_secret="a-unique-production-value",
            email_delivery_mode="resend",
            resend_api_key="resend-key",
            resend_from_email="accounts@example.com",
            turnstile_site_key="1x00000000000000000000AA",
            turnstile_secret_key="1x0000000000000000000000000000000AA",
        )

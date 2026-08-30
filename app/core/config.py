"""Validated environment configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    """Application settings loaded from environment variables and an optional .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Environment = "development"
    app_name: str = "Truth Hunter"
    app_version: str = "0.9.0-rc2"
    app_secret: SecretStr = SecretStr("development-only-change-me")
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_log_level: str = "INFO"
    app_trusted_hosts: str = "localhost,127.0.0.1,testserver,truthhunter"
    database_url: str = (
        "postgresql+psycopg://truthhunter:development-only-change-me@localhost:5432/truthhunter"
    )
    ai_provider: Literal["openai", "deepseek", "groq", "gemini", "openrouter"] = "openai"
    ai_api_key: SecretStr | None = None
    ai_model: str = "gpt-5-mini"
    ai_fallback_provider: Literal["openai", "deepseek", "groq"] | None = None
    ai_fallback_api_key: SecretStr | None = None
    ai_fallback_model: str | None = None
    ai_provider_order: str = "groq,gemini,openrouter,deepseek"
    allow_paid_ai_fallback: bool = False
    ai_max_paid_fallback_calls: int = Field(default=0, ge=0, le=50)
    groq_api_key: SecretStr | None = None
    groq_model: str = "openai/gpt-oss-120b"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    openrouter_api_key: SecretStr | None = None
    openrouter_model: str = "openrouter/free"
    deepseek_api_key: SecretStr | None = None
    deepseek_model: str = "deepseek-v4-flash"
    searxng_url: AnyHttpUrl = AnyHttpUrl("http://searxng:8080")
    brave_search_api_key: SecretStr | None = None
    brave_search_url: AnyHttpUrl = AnyHttpUrl("https://api.search.brave.com/res/v1/web/search")
    brave_search_max_queries_per_investigation: int = Field(default=2, ge=1, le=2)
    search_result_limit: int = Field(default=20, ge=1, le=50)
    search_delay_seconds: float = Field(default=1.0, ge=0, le=10)
    search_retry_attempts: int = Field(default=1, ge=0, le=2)
    source_useful_limit: int = Field(default=15, ge=1, le=15)
    source_evaluation_limit: int = Field(default=15, ge=1, le=30)
    ai_source_text_max_chars: int = Field(default=12_000, ge=1_000, le=50_000)
    fetch_timeout_seconds: float = Field(default=15.0, ge=1, le=60)
    fetch_max_bytes: int = Field(default=2_000_000, ge=10_000, le=5_000_000)
    fetch_redirect_limit: int = Field(default=4, ge=0, le=10)
    image_upload_max_bytes: int = Field(default=8_000_000, ge=100_000, le=15_000_000)
    image_upload_max_pixels: int = Field(default=20_000_000, ge=1_000_000, le=40_000_000)
    public_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost")
    support_url: AnyHttpUrl | None = None
    email_delivery_mode: Literal["development", "resend"] = "development"
    email_token_max_age_seconds: int = Field(default=86_400, ge=300, le=604_800)
    reset_token_max_age_seconds: int = Field(default=3_600, ge=300, le=86_400)
    auth_attempt_limit: int = Field(default=8, ge=3, le=50)
    auth_attempt_window_seconds: int = Field(default=900, ge=60, le=86_400)
    public_rate_limits_enabled: bool = True
    claim_submission_limit: int = Field(default=10, ge=1, le=100)
    investigation_start_limit: int = Field(default=5, ge=1, le=50)
    public_report_limit: int = Field(default=10, ge=1, le=100)
    public_limit_window_seconds: int = Field(default=3_600, ge=60, le=86_400)
    turnstile_site_key: str | None = None
    turnstile_secret_key: SecretStr | None = None
    turnstile_verify_url: AnyHttpUrl = AnyHttpUrl(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    )
    turnstile_timeout_seconds: float = Field(default=5.0, ge=1, le=15)
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    resend_api_key: SecretStr | None = None
    resend_from_email: str | None = None
    admin_emails: str = ""
    admin_access_max_age_seconds: int = Field(default=600, ge=300, le=3_600)
    admin_session_max_age_seconds: int = Field(default=1_800, ge=300, le=14_400)

    @field_validator("app_log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise ValueError("APP_LOG_LEVEL is not a supported logging level")
        return level

    @field_validator("database_url")
    @classmethod
    def require_postgresql(cls, value: str) -> str:
        if not value.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("DATABASE_URL must use PostgreSQL with Psycopg")
        return value

    @field_validator(
        "ai_api_key",
        "ai_fallback_provider",
        "ai_fallback_api_key",
        "ai_fallback_model",
        "groq_api_key",
        "gemini_api_key",
        "openrouter_api_key",
        "deepseek_api_key",
        "brave_search_api_key",
        "google_client_id",
        "google_client_secret",
        "resend_api_key",
        "resend_from_email",
        "support_url",
        "turnstile_site_key",
        "turnstile_secret_key",
        mode="before",
    )
    @classmethod
    def empty_fallback_values_are_unset(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("ai_provider_order")
    @classmethod
    def validate_provider_order(cls, value: str) -> str:
        providers = [item.strip() for item in value.split(",") if item.strip()]
        supported = {"groq", "gemini", "openrouter", "deepseek", "openai"}
        if not providers or len(providers) != len(set(providers)):
            raise ValueError("AI_PROVIDER_ORDER must contain unique provider names")
        if unknown := set(providers) - supported:
            raise ValueError(f"Unsupported providers in AI_PROVIDER_ORDER: {sorted(unknown)}")
        return ",".join(providers)

    @model_validator(mode="after")
    def reject_production_placeholders(self) -> "Settings":
        if self.app_env == "production" and "change-me" in self.app_secret.get_secret_value():
            raise ValueError("APP_SECRET must be replaced in production")
        if (
            self.app_env == "production"
            and self.ai_api_key is not None
            and "change-me" in self.ai_api_key.get_secret_value()
        ):
            raise ValueError("AI_API_KEY must be replaced in production")
        fallback_values = (
            self.ai_fallback_provider,
            self.ai_fallback_api_key,
            self.ai_fallback_model,
        )
        if any(value is not None for value in fallback_values) and not all(
            value is not None for value in fallback_values
        ):
            raise ValueError("All AI_FALLBACK settings must be provided together")
        if self.ai_fallback_provider == self.ai_provider:
            raise ValueError("AI_FALLBACK_PROVIDER must differ from AI_PROVIDER")
        if (
            self.app_env == "production"
            and self.ai_fallback_api_key is not None
            and "change-me" in self.ai_fallback_api_key.get_secret_value()
        ):
            raise ValueError("AI_FALLBACK_API_KEY must be replaced in production")
        if (
            self.app_env == "production"
            and self.brave_search_api_key is not None
            and "change-me" in self.brave_search_api_key.get_secret_value()
        ):
            raise ValueError("BRAVE_SEARCH_API_KEY must be replaced in production")
        if self.allow_paid_ai_fallback and self.ai_max_paid_fallback_calls == 0:
            raise ValueError(
                "AI_MAX_PAID_FALLBACK_CALLS must be positive when paid fallback is enabled"
            )
        if (self.google_client_id is None) != (self.google_client_secret is None):
            raise ValueError(
                "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured together"
            )
        if self.email_delivery_mode == "resend" and (
            self.resend_api_key is None or self.resend_from_email is None
        ):
            raise ValueError(
                "RESEND_API_KEY and RESEND_FROM_EMAIL are required for Resend delivery"
            )
        if (self.turnstile_site_key is None) != (self.turnstile_secret_key is None):
            raise ValueError("TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY are required together")
        test_turnstile_keys = {
            "1x00000000000000000000AA",
            "2x00000000000000000000AB",
            "3x00000000000000000000FF",
            "1x0000000000000000000000000000000AA",
            "2x0000000000000000000000000000000AA",
            "3x0000000000000000000000000000000AA",
        }
        configured_turnstile_keys = {
            self.turnstile_site_key,
            self.turnstile_secret_key.get_secret_value() if self.turnstile_secret_key else None,
        }
        if self.app_env == "production" and configured_turnstile_keys & test_turnstile_keys:
            raise ValueError("Cloudflare Turnstile test keys are forbidden in production")
        if self.app_env == "production" and not self.public_rate_limits_enabled:
            raise ValueError("PUBLIC_RATE_LIMITS_ENABLED must remain enabled in production")
        return self

    @property
    def provider_order(self) -> list[str]:
        return self.ai_provider_order.split(",")

    @property
    def trusted_hosts(self) -> list[str]:
        return [host.strip() for host in self.app_trusted_hosts.split(",") if host.strip()]

    @property
    def admin_email_allowlist(self) -> set[str]:
        return {email.strip().casefold() for email in self.admin_emails.split(",") if email.strip()}

    @property
    def turnstile_enabled(self) -> bool:
        return self.turnstile_site_key is not None and self.turnstile_secret_key is not None


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide validated settings object."""

    return Settings()

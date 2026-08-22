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
    app_version: str = "0.1.0"
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
    search_result_limit: int = Field(default=20, ge=1, le=50)
    source_useful_limit: int = Field(default=15, ge=1, le=15)
    fetch_timeout_seconds: float = Field(default=15.0, ge=1, le=60)
    fetch_max_bytes: int = Field(default=2_000_000, ge=10_000, le=5_000_000)
    fetch_redirect_limit: int = Field(default=4, ge=0, le=10)
    public_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost")
    email_delivery_mode: Literal["development", "resend"] = "development"
    email_token_max_age_seconds: int = Field(default=86_400, ge=300, le=604_800)
    reset_token_max_age_seconds: int = Field(default=3_600, ge=300, le=86_400)
    auth_attempt_limit: int = Field(default=8, ge=3, le=50)
    auth_attempt_window_seconds: int = Field(default=900, ge=60, le=86_400)
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    resend_api_key: SecretStr | None = None
    resend_from_email: str | None = None
    monetization_enabled: bool = False
    owner_payment_testing_enabled: bool = False
    payment_owner_emails: str = ""
    credit_pack_price_minor: int = Field(default=300, ge=1, le=1_000_000)
    credit_pack_currency: str = "EUR"
    credit_pack_size: int = Field(default=5, ge=1, le=10_000)
    paypal_environment: Literal["sandbox", "live"] = "sandbox"
    paypal_client_id: str | None = None
    paypal_client_secret: SecretStr | None = None
    paypal_webhook_id: str | None = None
    turnstile_site_key: str | None = None
    turnstile_secret_key: SecretStr | None = None
    anonymous_attempt_limit: int = Field(default=5, ge=1, le=100)
    anonymous_attempt_window_seconds: int = Field(default=86_400, ge=60, le=604_800)
    legal_review_approved: bool = False
    payment_record_retention_days: int = Field(default=3650, ge=1, le=7300)

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
        "google_client_id",
        "google_client_secret",
        "resend_api_key",
        "resend_from_email",
        "paypal_client_id",
        "paypal_client_secret",
        "paypal_webhook_id",
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

    @field_validator("credit_pack_currency")
    @classmethod
    def validate_credit_pack_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("CREDIT_PACK_CURRENCY must be a three-letter currency code")
        return normalized

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
        paypal_values = (
            self.paypal_client_id,
            self.paypal_client_secret,
            self.paypal_webhook_id,
        )
        if any(value is not None for value in paypal_values) and not all(
            value is not None for value in paypal_values
        ):
            raise ValueError("All PayPal credentials and PAYPAL_WEBHOOK_ID must be provided")
        if self.monetization_enabled and (
            not all(value is not None for value in paypal_values)
            or self.paypal_environment != "live"
            or self.turnstile_site_key is None
            or self.turnstile_secret_key is None
            or not self.legal_review_approved
        ):
            raise ValueError(
                "Public monetization requires live PayPal, Turnstile, and legal approval"
            )
        if self.owner_payment_testing_enabled and (
            not all(value is not None for value in paypal_values)
            or self.paypal_environment != "live"
            or not self.payment_owner_email_set
        ):
            raise ValueError(
                "Owner payment testing requires live PayPal credentials and an owner allowlist"
            )
        return self

    @property
    def provider_order(self) -> list[str]:
        return self.ai_provider_order.split(",")

    @property
    def trusted_hosts(self) -> list[str]:
        return [host.strip() for host in self.app_trusted_hosts.split(",") if host.strip()]

    @property
    def payment_owner_email_set(self) -> set[str]:
        return {
            email.strip().lower() for email in self.payment_owner_emails.split(",") if email.strip()
        }


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide validated settings object."""

    return Settings()

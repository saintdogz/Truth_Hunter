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
    ai_provider: Literal["openai"] = "openai"
    ai_api_key: SecretStr | None = None
    ai_model: str = "gpt-5-mini"
    searxng_url: AnyHttpUrl = AnyHttpUrl("http://searxng:8080")
    search_result_limit: int = Field(default=20, ge=1, le=50)
    source_useful_limit: int = Field(default=15, ge=1, le=15)
    fetch_timeout_seconds: float = Field(default=15.0, ge=1, le=60)
    fetch_max_bytes: int = Field(default=2_000_000, ge=10_000, le=5_000_000)
    fetch_redirect_limit: int = Field(default=4, ge=0, le=10)

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
        return self

    @property
    def trusted_hosts(self) -> list[str]:
        return [host.strip() for host in self.app_trusted_hosts.split(",") if host.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide validated settings object."""

    return Settings()

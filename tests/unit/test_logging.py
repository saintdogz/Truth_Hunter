"""Security checks for application log sanitization."""

import logging

from app.core.logging import SensitiveUrlFilter, redact_sensitive_urls


def test_discord_webhook_is_redacted_in_text_and_arguments() -> None:
    secret_url = "https://discord.com/api/webhooks/123456/super-secret-token"

    assert "super-secret-token" not in redact_sensitive_urls(f"POST {secret_url}")

    record = logging.LogRecord(
        "httpx",
        logging.INFO,
        __file__,
        1,
        "HTTP Request: %s",
        (secret_url,),
        None,
    )
    SensitiveUrlFilter().filter(record)

    assert "super-secret-token" not in record.getMessage()
    assert "/api/webhooks/[redacted]" in record.getMessage()


def test_non_sensitive_urls_are_unchanged() -> None:
    url = "https://truth.abathur.hu/health/live"
    assert redact_sensitive_urls(url) == url

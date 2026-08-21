"""Resend adapter payload and failure sanitization tests."""

from typing import Any

import httpx
import pytest

from app.auth.email import EmailDeliveryError, ResendEmailSender, create_account_email_sender
from app.core.config import Settings


def test_resend_sends_bilingual_verification_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        captured.update({"url": url, **kwargs})
        return httpx.Response(200, json={"id": "email-id"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    sender = ResendEmailSender("secret-key", "Truth Hunter <accounts@example.com>")

    sender.send_verification(
        "person@example.com", "https://truth.example/verify?token=a&lang=hu", "hu"
    )

    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["Authorization"] == "Bearer secret-key"
    payload = captured["json"]
    assert payload["from"] == "Truth Hunter <accounts@example.com>"
    assert payload["to"] == ["person@example.com"]
    assert "Erősítsd meg" in payload["subject"]
    assert "token=a&amp;lang=hu" in payload["html"]


def test_resend_failure_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    def failed_post(url: str, **kwargs: Any) -> httpx.Response:
        del kwargs
        return httpx.Response(401, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", failed_post)
    sender = ResendEmailSender("secret-key", "accounts@example.com")

    with pytest.raises(EmailDeliveryError, match="Transactional email delivery failed"):
        sender.send_password_reset("person@example.com", "https://example.com/reset", "en")


def test_resend_factory_requires_complete_configuration() -> None:
    settings = Settings(
        app_env="test",
        app_secret="test-secret",
        database_url="postgresql+psycopg://test:test@localhost/test",
        email_delivery_mode="resend",
        resend_api_key="secret-key",
        resend_from_email="Truth Hunter <accounts@example.com>",
    )

    assert isinstance(create_account_email_sender(settings), ResendEmailSender)

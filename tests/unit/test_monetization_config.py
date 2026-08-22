"""Activation-gate configuration tests."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def base() -> dict[str, object]:
    return {
        "app_env": "test",
        "app_secret": "activation-test-secret",
        "database_url": "postgresql+psycopg://test:test@localhost/test",
    }


def test_public_monetization_rejects_incomplete_prerequisites() -> None:
    with pytest.raises(ValidationError, match="Public monetization requires"):
        Settings(**base(), monetization_enabled=True)


def test_public_monetization_accepts_live_prerequisites() -> None:
    settings = Settings(
        **base(),
        monetization_enabled=True,
        paypal_environment="live",
        paypal_client_id="client",
        paypal_client_secret="secret",
        paypal_webhook_id="webhook",
        turnstile_site_key="site",
        turnstile_secret_key="turnstile",
        legal_review_approved=True,
    )
    assert settings.monetization_enabled is True


def test_owner_testing_requires_live_paypal_and_allowlist() -> None:
    with pytest.raises(ValidationError, match="Owner payment testing requires"):
        Settings(
            **base(),
            owner_payment_testing_enabled=True,
            paypal_client_id="client",
            paypal_client_secret="secret",
            paypal_webhook_id="webhook",
        )

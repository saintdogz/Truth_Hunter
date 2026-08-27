"""Durable public limits and Turnstile verification tests."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.abuse.limiter import allow_public_action
from app.abuse.turnstile import TurnstileError, verify_turnstile
from app.core.config import Settings
from app.db.base import Base


def test_rate_limit_is_durable_and_resets_after_window() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 27, tzinfo=timezone.utc)
    with Session(engine) as session:
        assert allow_public_action(
            session,
            action="claim_submission",
            key_hash="a" * 64,
            limit=2,
            window_seconds=60,
            now=now,
        )
        assert allow_public_action(
            session,
            action="claim_submission",
            key_hash="a" * 64,
            limit=2,
            window_seconds=60,
            now=now,
        )
        assert not allow_public_action(
            session,
            action="claim_submission",
            key_hash="a" * 64,
            limit=2,
            window_seconds=60,
            now=now,
        )
        assert allow_public_action(
            session,
            action="claim_submission",
            key_hash="a" * 64,
            limit=2,
            window_seconds=60,
            now=now + timedelta(seconds=61),
        )


def turnstile_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        turnstile_site_key="1x00000000000000000000AA",
        turnstile_secret_key="1x0000000000000000000000000000000AA",
    )


@pytest.mark.anyio
async def test_turnstile_accepts_successful_server_validation() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert b"secret=" in await request.aread()
        return httpx.Response(200, json={"success": True})

    assert await verify_turnstile(
        turnstile_settings(),
        "XXXX.DUMMY.TOKEN.XXXX",
        "127.0.0.1",
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.anyio
async def test_turnstile_rejects_invalid_or_oversized_tokens() -> None:
    settings = turnstile_settings()
    assert not await verify_turnstile(settings, None, None)
    assert not await verify_turnstile(settings, "x" * 2049, None)


@pytest.mark.anyio
async def test_turnstile_failure_is_distinct_from_invalid_challenge() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(TurnstileError):
        await verify_turnstile(
            turnstile_settings(),
            "token",
            None,
            transport=httpx.MockTransport(handler),
        )


@pytest.mark.anyio
async def test_production_turnstile_requires_expected_action_and_hostname() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        app_secret="a-unique-production-value",
        public_base_url="https://truth.abathur.hu",
        email_delivery_mode="resend",
        resend_api_key="resend-key",
        resend_from_email="accounts@example.com",
        turnstile_site_key="production-site-key",
        turnstile_secret_key="production-secret-key",
    )

    async def valid_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "action": "claim-submit",
                "hostname": "truth.abathur.hu",
            },
        )

    async def wrong_action_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": True, "action": "other", "hostname": "truth.abathur.hu"},
        )

    assert await verify_turnstile(
        settings, "token", None, transport=httpx.MockTransport(valid_handler)
    )
    assert not await verify_turnstile(
        settings, "token", None, transport=httpx.MockTransport(wrong_action_handler)
    )

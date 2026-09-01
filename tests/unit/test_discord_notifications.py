"""Privacy and reliability tests for Discord operational notifications."""

from uuid import uuid4

import httpx
import pytest

from app.core.config import Settings
from app.notifications.discord import DiscordNotifier, sanitize_claim


def discord_settings(**updates: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "test",
        "database_url": "postgresql+psycopg://truthhunter:test@localhost/test",
        "discord_webhook_url": "https://discord.com/api/webhooks/123/token",
    }
    values.update(updates)
    return Settings(**values)


def test_claim_excerpt_redacts_common_identifiers_and_mentions() -> None:
    excerpt = sanitize_claim(
        "Contact me@example.com or +36 30 123 4567 from 192.168.1.20 "
        "at https://example.com/reset?token=secret @everyone"
    )

    assert "me@example.com" not in excerpt
    assert "+36 30 123 4567" not in excerpt
    assert "192.168.1.20" not in excerpt
    assert "token=secret" not in excerpt
    assert "@everyone" not in excerpt
    assert "[email removed]" in excerpt


@pytest.mark.anyio
async def test_submitted_notification_contains_only_sanitized_excerpt() -> None:
    payloads: list[dict[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(__import__("json").loads(request.content))
        return httpx.Response(204)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    notifier = DiscordNotifier(discord_settings(), client=client)

    await notifier.submitted(uuid4(), "My email is private@example.com")
    await client.aclose()

    assert len(payloads) == 1
    assert "private@example.com" not in payloads[0]["content"]
    assert "[email removed]" in payloads[0]["content"]
    assert "user_id" not in payloads[0]["content"]
    assert "session" not in payloads[0]["content"]


@pytest.mark.anyio
async def test_disabled_notification_does_not_call_webhook() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(204)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    notifier = DiscordNotifier(discord_settings(discord_notifications_enabled=False), client=client)

    await notifier.failed(uuid4(), "A claim", status="SEARCH_FAILED")
    await client.aclose()

    assert calls == 0


@pytest.mark.anyio
async def test_webhook_failure_is_best_effort() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    notifier = DiscordNotifier(discord_settings(), client=client)

    await notifier.failed(uuid4(), "A claim", status="FAILED")
    await client.aclose()


def test_non_discord_webhook_is_rejected() -> None:
    with pytest.raises(ValueError, match="official Discord HTTPS webhook"):
        discord_settings(discord_webhook_url="https://example.com/api/webhooks/123/token")

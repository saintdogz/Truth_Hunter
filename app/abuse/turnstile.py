"""Cloudflare Turnstile server-side verification."""

from typing import Any
from uuid import uuid4

import httpx

from app.core.config import Settings


class TurnstileError(RuntimeError):
    """Raised when the verification service is unavailable."""


async def verify_turnstile(
    settings: Settings,
    token: str | None,
    remote_ip: str | None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bool:
    """Validate a single-use browser token with Cloudflare Siteverify."""
    if not settings.turnstile_enabled:
        return True
    if not token or len(token) > 2048:
        return False
    assert settings.turnstile_secret_key is not None
    payload = {
        "secret": settings.turnstile_secret_key.get_secret_value(),
        "response": token,
        "idempotency_key": str(uuid4()),
    }
    if remote_ip:
        payload["remoteip"] = remote_ip
    try:
        async with httpx.AsyncClient(
            timeout=settings.turnstile_timeout_seconds, transport=transport
        ) as client:
            response = await client.post(str(settings.turnstile_verify_url), data=payload)
            response.raise_for_status()
            body: dict[str, Any] = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise TurnstileError("Turnstile verification is unavailable") from exc
    if body.get("success") is not True:
        return False
    if settings.app_env == "production":
        expected_hostname = settings.public_base_url.host
        if body.get("action") != "claim-submit" or body.get("hostname") != expected_hostname:
            return False
    return True

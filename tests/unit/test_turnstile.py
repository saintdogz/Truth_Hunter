"""Cloudflare Turnstile adapter tests without external network calls."""

import httpx
import pytest

from app.payments.turnstile import CloudflareTurnstileVerifier


@pytest.mark.anyio
async def test_turnstile_accepts_only_successful_verification() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert b"secret=test-secret" in await request.aread()
        return httpx.Response(200, json={"success": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    verifier = CloudflareTurnstileVerifier("test-secret", client=client)
    try:
        assert await verifier.verify("valid-token", "192.0.2.1") is True
        assert await verifier.verify("", None) is False
    finally:
        await verifier.aclose()


@pytest.mark.anyio
async def test_turnstile_fails_closed_on_provider_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(503)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    verifier = CloudflareTurnstileVerifier("test-secret", client=client)
    try:
        assert await verifier.verify("token", None) is False
    finally:
        await verifier.aclose()

"""Cloudflare Turnstile verification for anonymous free investigations."""

from typing import Protocol

import httpx


class TurnstileVerifier(Protocol):
    async def verify(self, token: str, remote_ip: str | None) -> bool: ...


class CloudflareTurnstileVerifier:
    _VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

    def __init__(
        self,
        secret_key: str,
        *,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._secret_key = secret_key
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    async def verify(self, token: str, remote_ip: str | None) -> bool:
        if not token:
            return False
        payload = {"secret": self._secret_key, "response": token}
        if remote_ip:
            payload["remoteip"] = remote_ip
        try:
            response = await self._client.post(self._VERIFY_URL, data=payload)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError):
            return False
        return isinstance(body, dict) and body.get("success") is True

    async def aclose(self) -> None:
        await self._client.aclose()

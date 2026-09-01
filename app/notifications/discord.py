"""Best-effort Discord notifications without account or network identifiers."""

import logging
import re
from datetime import datetime
from uuid import UUID

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
IPV4_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{6,}\d)(?!\w)")
URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)


def sanitize_claim(claim: str, *, limit: int = 500) -> str:
    """Create a short excerpt with common personal identifiers removed."""

    sanitized = " ".join(claim.split())
    sanitized = EMAIL_PATTERN.sub("[email removed]", sanitized)
    sanitized = IPV4_PATTERN.sub("[IP removed]", sanitized)
    sanitized = PHONE_PATTERN.sub("[phone removed]", sanitized)
    sanitized = URL_PATTERN.sub("[link removed]", sanitized)
    sanitized = sanitized.replace("@", "@\u200b").replace("`", "'")
    if len(sanitized) > limit:
        sanitized = f"{sanitized[: limit - 1].rstrip()}…"
    return sanitized or "[empty after sanitization]"


class DiscordNotifier:
    """Send bounded webhook messages; delivery problems never escape this boundary."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._enabled = settings.discord_notifications_active
        self._webhook_url = (
            settings.discord_webhook_url.get_secret_value()
            if settings.discord_webhook_url
            else None
        )
        self._client = client
        self._timeout = settings.discord_webhook_timeout_seconds

    async def submitted(self, investigation_id: UUID, claim: str) -> None:
        await self._send(
            "🔎 **Investigation submitted**\n"
            f"`ID:` `{str(investigation_id)[:8]}`\n"
            f"`Claim excerpt (sanitized):`\n> {sanitize_claim(claim)}"
        )

    async def completed(
        self,
        investigation_id: UUID,
        claim: str,
        *,
        verdict: str,
        confidence: str,
        source_count: int,
        created_at: datetime,
        completed_at: datetime | None,
    ) -> None:
        duration = (
            max(0, round((completed_at - created_at).total_seconds()))
            if completed_at is not None
            else None
        )
        duration_text = f"{duration}s" if duration is not None else "unknown"
        await self._send(
            "✅ **Investigation completed**\n"
            f"`ID:` `{str(investigation_id)[:8]}` · `Verdict:` **{verdict}** · "
            f"`Confidence:` **{confidence}**\n"
            f"`Sources evaluated:` {source_count} · `Duration:` {duration_text}\n"
            f"`Claim excerpt (sanitized):`\n> {sanitize_claim(claim)}"
        )

    async def failed(self, investigation_id: UUID, claim: str, *, status: str) -> None:
        await self._send(
            "❌ **Investigation failed**\n"
            f"`ID:` `{str(investigation_id)[:8]}` · `Stage:` **{status}**\n"
            "`Credit:` not consumed\n"
            f"`Claim excerpt (sanitized):`\n> {sanitize_claim(claim)}"
        )

    async def _send(self, content: str) -> None:
        if not self._enabled or self._webhook_url is None:
            return
        try:
            if self._client is not None:
                response = await self._client.post(self._webhook_url, json={"content": content})
            else:
                async with httpx.AsyncClient(
                    timeout=self._timeout,
                    trust_env=False,
                ) as client:
                    response = await client.post(self._webhook_url, json={"content": content})
            response.raise_for_status()
        except Exception:  # noqa: BLE001 - notifications must never break an investigation
            logger.warning("Discord operational notification could not be delivered")

"""Conservative application logging configuration."""

import logging
import re
from typing import Any

DISCORD_WEBHOOK_PATTERN = re.compile(
    r"https://(?:canary\.|ptb\.)?(?:discord(?:app)?\.com)/api/webhooks/[^\s?'\"]+",
    flags=re.IGNORECASE,
)


def redact_sensitive_urls(value: Any) -> Any:
    """Redact webhook credentials in both formatted messages and logging arguments."""

    if isinstance(value, str):
        return DISCORD_WEBHOOK_PATTERN.sub("https://discord.com/api/webhooks/[redacted]", value)
    if isinstance(value, tuple):
        return tuple(redact_sensitive_urls(item) for item in value)
    if isinstance(value, dict):
        return {key: redact_sensitive_urls(item) for key, item in value.items()}
    return value


class SensitiveUrlFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_sensitive_urls(record.msg)
        record.args = redact_sensitive_urls(record.args)
        return True


def configure_logging(level: str) -> None:
    """Configure predictable logs without including configuration or secrets."""

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
    for handler in logging.getLogger().handlers:
        handler.addFilter(SensitiveUrlFilter())
    # Request-level INFO logs include complete URLs and add little operational value here.
    logging.getLogger("httpx").setLevel(logging.WARNING)

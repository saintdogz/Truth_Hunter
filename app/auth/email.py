"""Replaceable account-email boundary and Resend transactional adapter."""

import logging
from dataclasses import dataclass
from html import escape
from time import sleep
from typing import Protocol
from uuid import uuid4

import httpx

from app import __version__
from app.core.config import Settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    """Sanitized transactional delivery failure."""

    def __init__(self, category: str, *, status_code: int | None = None) -> None:
        super().__init__("Transactional email delivery failed")
        self.category = category
        self.status_code = status_code


class AccountEmailSender(Protocol):
    def send_verification(self, email: str, url: str, language: str) -> None: ...

    def send_password_reset(self, email: str, url: str, language: str) -> None: ...

    def send_admin_access(self, email: str, url: str, language: str) -> None: ...


@dataclass(frozen=True)
class DevelopmentEmail:
    kind: str
    recipient: str
    url: str


class DevelopmentEmailSender:
    """Keep links in process memory; never log tokens or recipient addresses."""

    def __init__(self) -> None:
        self.outbox: list[DevelopmentEmail] = []

    def send_verification(self, email: str, url: str, language: str) -> None:
        del language
        self.outbox.append(DevelopmentEmail("verification", email, url))

    def send_password_reset(self, email: str, url: str, language: str) -> None:
        del language
        self.outbox.append(DevelopmentEmail("password_reset", email, url))

    def send_admin_access(self, email: str, url: str, language: str) -> None:
        del language
        self.outbox.append(DevelopmentEmail("admin_access", email, url))


class ResendEmailSender:
    endpoint = "https://api.resend.com/emails"

    def __init__(
        self,
        api_key: str,
        from_email: str,
        *,
        timeout_seconds: float = 10.0,
        max_attempts: int = 3,
    ) -> None:
        self._api_key = api_key
        self._from_email = from_email
        self._timeout = timeout_seconds
        self._max_attempts = max_attempts

    def send_verification(self, email: str, url: str, language: str) -> None:
        copy = (
            (
                "Erősítsd meg a Truth Hunter-fiókodat",
                "E-mail-cím megerősítése",
                "A fiókod aktiválásához kattints az alábbi gombra.",
                "Fiók megerősítése",
            )
            if language == "hu"
            else (
                "Verify your Truth Hunter account",
                "Verify your email address",
                "Activate your account by clicking the button below.",
                "Verify account",
            )
        )
        self._send(email, *copy, url, "verification")

    def send_password_reset(self, email: str, url: str, language: str) -> None:
        copy = (
            (
                "Truth Hunter-jelszó visszaállítása",
                "Jelszó visszaállítása",
                "Az új jelszó beállításához kattints az alábbi gombra.",
                "Új jelszó beállítása",
            )
            if language == "hu"
            else (
                "Reset your Truth Hunter password",
                "Reset your password",
                "Set a new password by clicking the button below.",
                "Choose new password",
            )
        )
        self._send(email, *copy, url, "password_reset")

    def send_admin_access(self, email: str, url: str, language: str) -> None:
        copy = (
            (
                "Truth Hunter admin belépés",
                "Admin belépés megerősítése",
                "A privát admin irányítópult megnyitásához kattints az alábbi gombra. "
                "A hivatkozás 10 percig használható.",
                "Admin irányítópult megnyitása",
            )
            if language == "hu"
            else (
                "Truth Hunter admin access",
                "Confirm admin access",
                "Open the private admin dashboard using the button below. "
                "This link is valid for 10 minutes.",
                "Open admin dashboard",
            )
        )
        self._send(email, *copy, url, "admin_access")

    def _send(
        self,
        recipient: str,
        subject: str,
        heading: str,
        message: str,
        button: str,
        url: str,
        tag: str,
    ) -> None:
        safe_url = escape(url, quote=True)
        html = (
            '<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;'
            'background:#0f171f;color:#e8edf2;padding:32px;border-radius:12px">'
            f'<h1 style="font-size:24px">{escape(heading)}</h1>'
            f'<p style="line-height:1.6;color:#b7c4ca">{escape(message)}</p>'
            f'<p><a href="{safe_url}" style="display:inline-block;background:#68d1b2;'
            "color:#062019;padding:12px 18px;border-radius:8px;text-decoration:none;"
            f'font-weight:bold">{escape(button)}</a></p>'
            '<p style="font-size:12px;color:#82939f">Truth Hunter</p></div>'
        )
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "User-Agent": f"Truth-Hunter/{__version__}",
            "Idempotency-Key": f"truth-hunter-{tag}-{uuid4()}",
        }
        payload = {
            "from": self._from_email,
            "to": [recipient],
            "subject": subject,
            "html": html,
            "tags": [{"name": "message_type", "value": tag}],
        }
        for attempt in range(1, self._max_attempts + 1):
            category = "unknown"
            status_code: int | None = None
            retryable = False
            try:
                response = httpx.post(
                    self.endpoint,
                    headers=headers,
                    json=payload,
                    timeout=self._timeout,
                )
                response.raise_for_status()
                if attempt > 1:
                    logger.info("email_delivery_recovered type=%s attempts=%d", tag, attempt)
                return
            except httpx.TimeoutException as exc:
                category = "timeout"
                retryable = True
                cause: Exception = exc
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if status_code == 429:
                    category = "rate_limit"
                    retryable = True
                elif status_code >= 500:
                    category = "provider_unavailable"
                    retryable = True
                else:
                    category = "provider_rejected"
                cause = exc
            except httpx.RequestError as exc:
                category = "network"
                retryable = True
                cause = exc
            except ValueError as exc:
                category = "invalid_request"
                cause = exc

            if retryable and attempt < self._max_attempts:
                logger.warning(
                    "email_delivery_retry type=%s category=%s status=%s attempt=%d",
                    tag,
                    category,
                    status_code,
                    attempt,
                )
                sleep(0.25 * attempt)
                continue
            logger.error(
                "email_delivery_failed type=%s category=%s status=%s attempts=%d",
                tag,
                category,
                status_code,
                attempt,
            )
            raise EmailDeliveryError(category, status_code=status_code) from cause


def create_account_email_sender(settings: Settings) -> AccountEmailSender:
    if settings.email_delivery_mode == "resend":
        if settings.resend_api_key is None or settings.resend_from_email is None:
            raise ValueError("Resend email delivery is not fully configured")
        return ResendEmailSender(
            settings.resend_api_key.get_secret_value(), settings.resend_from_email
        )
    return DevelopmentEmailSender()

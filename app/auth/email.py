"""Replaceable account-email boundary and Resend transactional adapter."""

from dataclasses import dataclass
from html import escape
from typing import Protocol

import httpx

from app.core.config import Settings


class EmailDeliveryError(RuntimeError):
    """Sanitized transactional delivery failure."""


class AccountEmailSender(Protocol):
    def send_verification(self, email: str, url: str, language: str) -> None: ...

    def send_password_reset(self, email: str, url: str, language: str) -> None: ...

    def send_purchase_confirmation(
        self, email: str, account_url: str, balance: int, language: str
    ) -> None: ...


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

    def send_purchase_confirmation(
        self, email: str, account_url: str, balance: int, language: str
    ) -> None:
        del balance, language
        self.outbox.append(DevelopmentEmail("purchase_confirmation", email, account_url))


class ResendEmailSender:
    endpoint = "https://api.resend.com/emails"

    def __init__(self, api_key: str, from_email: str, *, timeout_seconds: float = 10.0) -> None:
        self._api_key = api_key
        self._from_email = from_email
        self._timeout = timeout_seconds

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

    def send_purchase_confirmation(
        self, email: str, account_url: str, balance: int, language: str
    ) -> None:
        copy = (
            (
                "Sikeres Truth Hunter-vásárlás",
                "Öt vizsgálati kredit hozzáadva",
                f"A fizetést megerősítettük. Jelenlegi egyenleged: {balance} kredit.",
                "Fiók megnyitása",
            )
            if language == "hu"
            else (
                "Truth Hunter purchase confirmed",
                "Five investigation credits added",
                f"Your payment was confirmed. Your current balance is {balance} credits.",
                "Open account",
            )
        )
        self._send(email, *copy, account_url, "purchase_confirmation")

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
        try:
            response = httpx.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "User-Agent": "Truth-Hunter/0.1.0",
                },
                json={
                    "from": self._from_email,
                    "to": [recipient],
                    "subject": subject,
                    "html": html,
                    "tags": [{"name": "message_type", "value": tag}],
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
        except (httpx.HTTPError, ValueError) as exc:
            raise EmailDeliveryError("Transactional email delivery failed") from exc


def create_account_email_sender(settings: Settings) -> AccountEmailSender:
    if settings.email_delivery_mode == "resend":
        if settings.resend_api_key is None or settings.resend_from_email is None:
            raise ValueError("Resend email delivery is not fully configured")
        return ResendEmailSender(
            settings.resend_api_key.get_secret_value(), settings.resend_from_email
        )
    return DevelopmentEmailSender()

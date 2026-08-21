"""Replaceable account-email boundary with a safe development implementation."""

from dataclasses import dataclass
from typing import Protocol


class AccountEmailSender(Protocol):
    def send_verification(self, email: str, url: str) -> None: ...

    def send_password_reset(self, email: str, url: str) -> None: ...


@dataclass(frozen=True)
class DevelopmentEmail:
    kind: str
    recipient: str
    url: str


class DevelopmentEmailSender:
    """Keep links in process memory; never log tokens or recipient addresses."""

    def __init__(self) -> None:
        self.outbox: list[DevelopmentEmail] = []

    def send_verification(self, email: str, url: str) -> None:
        self.outbox.append(DevelopmentEmail("verification", email, url))

    def send_password_reset(self, email: str, url: str) -> None:
        self.outbox.append(DevelopmentEmail("password_reset", email, url))

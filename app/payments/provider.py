"""Replaceable payment-provider boundary and PayPal Orders v2 adapter."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import Settings


class PaymentProviderError(RuntimeError):
    """Sanitized external payment-provider failure."""


@dataclass(frozen=True)
class CreatedOrder:
    order_id: str
    status: str


@dataclass(frozen=True)
class CapturedOrder:
    order_id: str
    capture_id: str
    status: str
    amount_minor: int
    currency: str


class PaymentProvider(Protocol):
    client_id: str

    async def create_order(
        self,
        *,
        request_id: str,
        amount_minor: int,
        currency: str,
        description: str,
        custom_id: str,
    ) -> CreatedOrder: ...

    async def capture_order(self, order_id: str, *, request_id: str) -> CapturedOrder: ...

    async def verify_webhook(self, headers: dict[str, str], event: dict[str, object]) -> bool: ...

    async def aclose(self) -> None: ...


class PayPalOrdersProvider:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        webhook_id: str,
        *,
        environment: str,
        timeout: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.client_id = client_id
        self._client_secret = client_secret
        self._webhook_id = webhook_id
        self._base_url = (
            "https://api-m.paypal.com"
            if environment == "live"
            else "https://api-m.sandbox.paypal.com"
        )
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None

    async def create_order(
        self,
        *,
        request_id: str,
        amount_minor: int,
        currency: str,
        description: str,
        custom_id: str,
    ) -> CreatedOrder:
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "custom_id": custom_id,
                    "description": description,
                    "amount": {
                        "currency_code": currency,
                        "value": _minor_to_decimal(amount_minor),
                    },
                }
            ],
        }
        data = await self._request(
            "POST",
            "/v2/checkout/orders",
            request_id=request_id,
            json=payload,
        )
        order_id = data.get("id")
        status = data.get("status")
        if not isinstance(order_id, str) or not isinstance(status, str):
            raise PaymentProviderError("PayPal returned an invalid order")
        return CreatedOrder(order_id, status)

    async def capture_order(self, order_id: str, *, request_id: str) -> CapturedOrder:
        data = await self._request(
            "POST",
            f"/v2/checkout/orders/{order_id}/capture",
            request_id=request_id,
            json={},
        )
        try:
            capture = data["purchase_units"][0]["payments"]["captures"][0]  # type: ignore[index]
            amount = capture["amount"]
            capture_id = capture["id"]
            capture_status = capture["status"]
            currency = amount["currency_code"]
            amount_minor = _decimal_to_minor(amount["value"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise PaymentProviderError("PayPal returned an invalid capture") from exc
        if not all(isinstance(value, str) for value in (capture_id, capture_status, currency)):
            raise PaymentProviderError("PayPal returned an invalid capture")
        return CapturedOrder(
            order_id=order_id,
            capture_id=capture_id,
            status=capture_status,
            amount_minor=amount_minor,
            currency=currency,
        )

    async def verify_webhook(self, headers: dict[str, str], event: dict[str, object]) -> bool:
        required = {
            "transmission_id": headers.get("paypal-transmission-id"),
            "transmission_time": headers.get("paypal-transmission-time"),
            "cert_url": headers.get("paypal-cert-url"),
            "auth_algo": headers.get("paypal-auth-algo"),
            "transmission_sig": headers.get("paypal-transmission-sig"),
        }
        if any(not value for value in required.values()):
            return False
        payload = {**required, "webhook_id": self._webhook_id, "webhook_event": event}
        data = await self._request(
            "POST", "/v1/notifications/verify-webhook-signature", json=payload
        )
        return data.get("verification_status") == "SUCCESS"

    async def _access_token(self) -> str:
        try:
            response = await self._client.post(
                f"{self._base_url}/v1/oauth2/token",
                auth=(self.client_id, self._client_secret),
                headers={"Accept": "application/json"},
                data={"grant_type": "client_credentials"},
            )
            response.raise_for_status()
            token = response.json().get("access_token")
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise PaymentProviderError("PayPal authentication failed") from exc
        if not isinstance(token, str) or not token:
            raise PaymentProviderError("PayPal authentication failed")
        return token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        request_id: str | None = None,
        json: Mapping[str, object],
    ) -> dict[str, object]:
        token = await self._access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        if request_id:
            headers["PayPal-Request-Id"] = request_id[:108]
        try:
            response = await self._client.request(
                method, f"{self._base_url}{path}", headers=headers, json=json
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PaymentProviderError("PayPal request failed") from exc
        if not isinstance(payload, dict):
            raise PaymentProviderError("PayPal returned an invalid response")
        return payload

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def _minor_to_decimal(amount_minor: int) -> str:
    return f"{amount_minor // 100}.{amount_minor % 100:02d}"


def _decimal_to_minor(value: object) -> int:
    if not isinstance(value, str) or "." not in value:
        raise ValueError("Invalid decimal amount")
    whole, fraction = value.split(".", 1)
    if not whole.isdigit() or not fraction.isdigit() or len(fraction) > 2:
        raise ValueError("Invalid decimal amount")
    return int(whole) * 100 + int(fraction.ljust(2, "0"))


def create_payment_provider(settings: Settings) -> PaymentProvider | None:
    if (
        settings.paypal_client_id is None
        or settings.paypal_client_secret is None
        or settings.paypal_webhook_id is None
    ):
        return None
    return PayPalOrdersProvider(
        settings.paypal_client_id,
        settings.paypal_client_secret.get_secret_value(),
        settings.paypal_webhook_id,
        environment=settings.paypal_environment,
    )

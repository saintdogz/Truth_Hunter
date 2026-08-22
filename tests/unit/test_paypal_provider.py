"""PayPal Orders v2 adapter contract tests using an in-memory HTTP transport."""

import json

import httpx
import pytest

from app.payments.provider import PayPalOrdersProvider


@pytest.mark.anyio
async def test_create_and_capture_paypal_order() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "token"})
        if request.url.path == "/v2/checkout/orders":
            payload = json.loads(request.content)
            assert payload["intent"] == "CAPTURE"
            assert payload["purchase_units"][0]["amount"] == {
                "currency_code": "EUR",
                "value": "3.00",
            }
            return httpx.Response(201, json={"id": "ORDER-1", "status": "CREATED"})
        if request.url.path == "/v2/checkout/orders/ORDER-1/capture":
            return httpx.Response(
                201,
                json={
                    "id": "ORDER-1",
                    "status": "COMPLETED",
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": "CAPTURE-1",
                                        "status": "COMPLETED",
                                        "amount": {
                                            "currency_code": "EUR",
                                            "value": "3.00",
                                        },
                                    }
                                ]
                            }
                        }
                    ],
                },
            )
        raise AssertionError(f"Unexpected request: {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = PayPalOrdersProvider(
        "client-id", "client-secret", "webhook-id", environment="live", client=client
    )

    created = await provider.create_order(
        request_id="request-1",
        amount_minor=300,
        currency="EUR",
        description="Five investigation credits",
        custom_id="user-id",
    )
    captured = await provider.capture_order("ORDER-1", request_id="request-2")

    assert created.order_id == "ORDER-1"
    assert captured.capture_id == "CAPTURE-1"
    assert captured.amount_minor == 300
    assert requests[1].headers["paypal-request-id"] == "request-1"
    await client.aclose()


@pytest.mark.anyio
async def test_paypal_webhook_uses_postback_verification() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "token"})
        if request.url.path == "/v1/notifications/verify-webhook-signature":
            payload = json.loads(request.content)
            assert payload["webhook_id"] == "webhook-id"
            assert payload["webhook_event"]["id"] == "EVENT-1"
            return httpx.Response(200, json={"verification_status": "SUCCESS"})
        raise AssertionError(f"Unexpected request: {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = PayPalOrdersProvider(
        "client-id", "client-secret", "webhook-id", environment="sandbox", client=client
    )
    headers = {
        "paypal-transmission-id": "transmission",
        "paypal-transmission-time": "2026-08-22T00:00:00Z",
        "paypal-cert-url": "https://api-m.paypal.com/cert",
        "paypal-auth-algo": "SHA256withRSA",
        "paypal-transmission-sig": "signature",
    }

    assert await provider.verify_webhook(headers, {"id": "EVENT-1"}) is True
    assert await provider.verify_webhook({}, {"id": "EVENT-1"}) is False
    await client.aclose()

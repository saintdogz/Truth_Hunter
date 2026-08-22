"""Feature-flagged PayPal checkout, capture, webhook, and credit history routes."""

from contextlib import suppress
from typing import Annotated, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.email import AccountEmailSender, EmailDeliveryError
from app.auth.session import current_user
from app.core.config import Settings, get_settings
from app.db.models import User
from app.db.session import get_session
from app.payments.access import monetization_allowed
from app.payments.provider import PaymentProvider, PaymentProviderError
from app.payments.service import MonetizationError, MonetizationService
from app.web.csrf import csrf_token, require_csrf
from app.web.i18n import (
    account_copy_for,
    language_from_request,
    language_switch_url,
    payment_copy_for,
)

router = APIRouter()


def _provider(request: Request) -> PaymentProvider | None:
    return cast(PaymentProvider | None, request.app.state.payment_provider)


def _email_sender(request: Request) -> AccountEmailSender:
    return cast(AccountEmailSender, request.app.state.account_email_sender)


def _user_or_redirect(
    request: Request, session: Session, settings: Settings
) -> User | RedirectResponse:
    user = current_user(request, session, settings)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return user


def _checkout_allowed(user: User, settings: Settings) -> bool:
    return monetization_allowed(user, settings)


@router.get("/credits", response_class=HTMLResponse, include_in_schema=False)
def credits_page(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    user = _user_or_redirect(request, session, settings)
    if isinstance(user, RedirectResponse):
        return user
    if not _checkout_allowed(user, settings):
        raise HTTPException(status_code=404)
    service = MonetizationService(session, settings)
    service.record_event("offer_viewed", user=user)
    language = language_from_request(request)
    provider = _provider(request)
    context = {
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "language": language,
        "a": account_copy_for(language),
        "p": payment_copy_for(language),
        "language_urls": {
            "en": language_switch_url(request, "en"),
            "hu": language_switch_url(request, "hu"),
        },
        "current_user": user,
        "show_monetization": True,
        "credit_balance": service.balance(user),
        "payments": service.purchase_history(user),
        "csrf_token": csrf_token(request),
        "paypal_client_id": provider.client_id if provider else None,
        "price_minor": settings.credit_pack_price_minor,
        "currency": settings.credit_pack_currency,
        "pack_size": settings.credit_pack_size,
    }
    return cast(
        Response,
        request.app.state.templates.TemplateResponse(
            request=request, name="credits.html", context=context
        ),
    )


@router.post("/api/paypal/orders", tags=["payments"])
async def create_paypal_order(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    require_csrf(request, request.headers.get("x-csrf-token", ""))
    user = current_user(request, session, settings)
    provider = _provider(request)
    if user is None:
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    if not _checkout_allowed(user, settings) or provider is None:
        return JSONResponse({"detail": "Checkout is unavailable"}, status_code=503)
    request_id = str(uuid4())
    try:
        order = await provider.create_order(
            request_id=request_id,
            amount_minor=settings.credit_pack_price_minor,
            currency=settings.credit_pack_currency,
            description=f"{settings.credit_pack_size} Truth Hunter investigation credits",
            custom_id=str(user.id),
        )
        MonetizationService(session, settings).record_created_order(user, order.order_id)
    except (PaymentProviderError, MonetizationError):
        return JSONResponse({"detail": "Payment could not be started"}, status_code=502)
    return JSONResponse({"id": order.order_id})


@router.post("/api/paypal/orders/{order_id}/capture", tags=["payments"])
async def capture_paypal_order(
    request: Request,
    order_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    require_csrf(request, request.headers.get("x-csrf-token", ""))
    user = current_user(request, session, settings)
    provider = _provider(request)
    if user is None:
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    if not _checkout_allowed(user, settings) or provider is None:
        return JSONResponse({"detail": "Checkout is unavailable"}, status_code=503)
    service = MonetizationService(session, settings)
    try:
        service.payment_for_user(user, order_id)
        capture = await provider.capture_order(order_id, request_id=str(uuid4()))
        if capture.status != "COMPLETED":
            raise MonetizationError("Payment was not completed")
        service.complete_payment(
            user,
            order_id,
            capture.capture_id,
            capture.amount_minor,
            capture.currency,
        )
    except (PaymentProviderError, MonetizationError):
        return JSONResponse({"detail": "Payment could not be completed"}, status_code=502)
    balance = service.balance(user)
    account_url = f"{str(settings.public_base_url).rstrip('/')}/account"
    with suppress(EmailDeliveryError):
        _email_sender(request).send_purchase_confirmation(
            user.email, account_url, balance, language_from_request(request)
        )
    return JSONResponse({"status": "completed", "balance": balance})


@router.post("/webhooks/paypal", tags=["payments"])
async def paypal_webhook(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    provider = _provider(request)
    if provider is None:
        return JSONResponse({"detail": "Webhook unavailable"}, status_code=503)
    try:
        event = await request.json()
    except ValueError:
        return JSONResponse({"detail": "Invalid event"}, status_code=400)
    if not isinstance(event, dict):
        return JSONResponse({"detail": "Invalid event"}, status_code=400)
    headers = {key.lower(): value for key, value in request.headers.items()}
    if not await provider.verify_webhook(headers, event):
        return JSONResponse({"detail": "Invalid signature"}, status_code=400)
    try:
        MonetizationService(session, settings).process_verified_webhook(event)
    except MonetizationError:
        return JSONResponse({"detail": "Event could not be processed"}, status_code=422)
    return JSONResponse({"status": "accepted"})

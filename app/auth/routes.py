"""Server-rendered Phase 4 account routes."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.email import AccountEmailSender, EmailDeliveryError
from app.auth.rate_limit import AuthRateLimiter
from app.auth.service import (
    AccountError,
    AccountService,
    AuthenticationError,
    InvalidTokenError,
)
from app.auth.session import current_user, sign_in, sign_out
from app.core.config import Settings, get_settings
from app.db.models import User
from app.db.session import get_session
from app.payments.service import MonetizationService
from app.payments.view import payment_context
from app.web.csrf import csrf_token, require_csrf
from app.web.i18n import (
    STATUS_COPY,
    account_copy_for,
    account_error_for,
    language_from_request,
    language_switch_url,
    payment_copy_for,
)

router = APIRouter()


def _render(
    request: Request,
    template: str,
    context: dict[str, object],
    *,
    status_code: int = 200,
) -> Response:
    language = language_from_request(request)
    base: dict[str, object] = {
        "app_name": request.app.state.settings.app_name,
        "app_version": request.app.state.settings.app_version,
        "language": language,
        "a": account_copy_for(language),
        "p": payment_copy_for(language),
        "status_copy": STATUS_COPY[language],
        "language_urls": {
            "en": language_switch_url(request, "en"),
            "hu": language_switch_url(request, "hu"),
        },
        "csrf_token": csrf_token(request),
    }
    base.update(payment_context(request))
    base.update(context)
    return cast(
        Response,
        request.app.state.templates.TemplateResponse(
            request=request, name=template, context=base, status_code=status_code
        ),
    )


def _email_sender(request: Request) -> AccountEmailSender:
    return cast(AccountEmailSender, request.app.state.account_email_sender)


def _limiter(request: Request) -> AuthRateLimiter:
    return cast(AuthRateLimiter, request.app.state.auth_rate_limiter)


def _rate_key(request: Request, email: str, action: str) -> str:
    host = request.client.host if request.client else "unknown"
    digest_email = email.strip().lower()[:320]
    return f"{action}:{host}:{digest_email}"


def _account_url(settings: Settings, path: str, token: str, language: str) -> str:
    return f"{str(settings.public_base_url).rstrip('/')}{path}?token={token}&lang={language}"


def _development_email_url(settings: Settings, url: str | None) -> str | None:
    if settings.app_env == "production" or settings.email_delivery_mode != "development":
        return None
    return url


@router.get("/register", response_class=HTMLResponse, include_in_schema=False)
def register_page(request: Request) -> Response:
    return _render(request, "register.html", {"error": None, "email": ""})


@router.post("/register", response_class=HTMLResponse, include_in_schema=False)
def register(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    require_csrf(request, csrf)
    language = language_from_request(request)
    copy = account_copy_for(language)
    key = _rate_key(request, email, "register")
    if not _limiter(request).allow(key):
        return _render(
            request,
            "register.html",
            {"error": copy["too_many"], "email": email},
            status_code=429,
        )
    service = AccountService(session, settings)
    try:
        user = service.register(email, password)
    except AccountError as exc:
        return _render(
            request,
            "register.html",
            {"error": account_error_for(language, str(exc)), "email": email},
            status_code=400,
        )
    token = service.verification_token(user)
    url = _account_url(settings, "/verify-email", token, language)
    try:
        _email_sender(request).send_verification(user.email, url, language)
    except EmailDeliveryError:
        service.discard_unverified_registration(user)
        return _render(
            request,
            "register.html",
            {"error": copy["email_unavailable"], "email": email},
            status_code=503,
        )
    return _render(
        request,
        "account_message.html",
        {
            "title": copy["check_email"],
            "message": copy["verify_message"],
            "development_url": _development_email_url(settings, url),
        },
        status_code=201,
    )


@router.get("/verify-email", response_class=HTMLResponse, include_in_schema=False)
def verify_email(
    request: Request,
    token: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    language = language_from_request(request)
    copy = account_copy_for(language)
    try:
        user = AccountService(session, settings).verify_email(token)
    except InvalidTokenError as exc:
        return _render(
            request,
            "account_message.html",
            {
                "title": copy["verification_failed"],
                "message": account_error_for(language, str(exc)),
                "development_url": None,
            },
            status_code=400,
        )
    sign_in(request, user)
    AccountService(session, settings).claim_guest_investigations(
        user, cast(str | None, request.session.get("guest_session_id"))
    )
    return RedirectResponse("/history", status_code=303)


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request) -> Response:
    return _render(request, "login.html", {"error": None, "email": ""})


@router.post("/login", response_class=HTMLResponse, include_in_schema=False)
def login(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    require_csrf(request, csrf)
    language = language_from_request(request)
    copy = account_copy_for(language)
    key = _rate_key(request, email, "login")
    limiter = _limiter(request)
    if not limiter.allow(key):
        return _render(
            request,
            "login.html",
            {"error": copy["too_many"], "email": email},
            status_code=429,
        )
    service = AccountService(session, settings)
    try:
        user = service.authenticate(email, password)
    except AuthenticationError as exc:
        return _render(
            request,
            "login.html",
            {"error": account_error_for(language, str(exc)), "email": email},
            status_code=400,
        )
    limiter.clear(key)
    guest_id = request.session.get("guest_session_id")
    sign_in(request, user)
    service.claim_guest_investigations(user, guest_id if isinstance(guest_id, str) else None)
    return RedirectResponse("/history", status_code=303)


@router.post("/logout", include_in_schema=False)
def logout(request: Request, csrf: Annotated[str, Form()]) -> Response:
    require_csrf(request, csrf)
    sign_out(request)
    return RedirectResponse("/", status_code=303)


@router.get("/forgot-password", response_class=HTMLResponse, include_in_schema=False)
def forgot_page(request: Request) -> Response:
    return _render(request, "forgot_password.html", {"error": None})


@router.post("/forgot-password", response_class=HTMLResponse, include_in_schema=False)
def forgot_password(
    request: Request,
    email: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    require_csrf(request, csrf)
    language = language_from_request(request)
    copy = account_copy_for(language)
    key = _rate_key(request, email, "reset")
    if not _limiter(request).allow(key):
        return _render(
            request,
            "account_message.html",
            {
                "title": copy["request_received"],
                "message": copy["reset_message"],
                "development_url": None,
            },
        )
    service = AccountService(session, settings)
    user = service.find_active_user(email)
    development_url = None
    if user is not None and user.password_hash is not None:
        token = service.password_reset_token(user)
        development_url = _account_url(settings, "/reset-password", token, language)
        try:
            _email_sender(request).send_password_reset(user.email, development_url, language)
        except EmailDeliveryError:
            development_url = None
    return _render(
        request,
        "account_message.html",
        {
            "title": copy["request_received"],
            "message": copy["reset_message"],
            "development_url": _development_email_url(settings, development_url),
        },
    )


@router.get("/reset-password", response_class=HTMLResponse, include_in_schema=False)
def reset_page(request: Request, token: str) -> Response:
    return _render(request, "reset_password.html", {"error": None, "token": token})


@router.post("/reset-password", response_class=HTMLResponse, include_in_schema=False)
def reset_password(
    request: Request,
    token: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    require_csrf(request, csrf)
    language = language_from_request(request)
    try:
        AccountService(session, settings).reset_password(token, password)
    except AccountError as exc:
        return _render(
            request,
            "reset_password.html",
            {"error": account_error_for(language, str(exc)), "token": token},
            status_code=400,
        )
    sign_out(request)
    return RedirectResponse("/login?reset=1", status_code=303)


def _require_user(request: Request, session: Session, settings: Settings) -> User | None:
    return current_user(request, session, settings)


@router.get("/history", response_class=HTMLResponse, include_in_schema=False)
def history(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    user = _require_user(request, session, settings)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    investigations = AccountService(session, settings).history(user)
    return _render(
        request, "history.html", {"current_user": user, "investigations": investigations}
    )


@router.get("/account", response_class=HTMLResponse, include_in_schema=False)
def account(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    user = _require_user(request, session, settings)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    payment = payment_context(request)
    show_monetization = payment.get("show_monetization") is True
    service = MonetizationService(session, settings)
    return _render(
        request,
        "account.html",
        {
            "current_user": user,
            "error": None,
            "payments": service.purchase_history(user) if show_monetization else [],
        },
    )


@router.post("/account/delete", include_in_schema=False)
def delete_account(
    request: Request,
    csrf: Annotated[str, Form()],
    confirmation: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    require_csrf(request, csrf)
    user = _require_user(request, session, settings)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if confirmation != "DELETE":
        copy = account_copy_for(language_from_request(request))
        return _render(
            request,
            "account.html",
            {"current_user": user, "error": copy["delete_error"]},
            status_code=400,
        )
    AccountService(session, settings).delete_account(user)
    sign_out(request)
    return RedirectResponse("/login?deleted=1", status_code=303)

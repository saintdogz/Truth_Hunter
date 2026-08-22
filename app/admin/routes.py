"""Private, read-only operational dashboard routes."""

import logging
import time
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.admin.security import create_admin_token, verify_admin_token
from app.admin.service import dashboard_snapshot
from app.auth.email import AccountEmailSender, EmailDeliveryError
from app.auth.rate_limit import AuthRateLimiter
from app.auth.session import current_user
from app.core.config import Settings, get_settings
from app.db.models import User
from app.db.session import get_session
from app.web.csrf import csrf_token, require_csrf
from app.web.i18n import account_copy_for, language_from_request, language_switch_url

router = APIRouter(prefix="/admin", include_in_schema=False)
logger = logging.getLogger(__name__)


def _render(request: Request, template: str, context: dict[str, object]) -> Response:
    language = language_from_request(request)
    base: dict[str, object] = {
        "app_name": request.app.state.settings.app_name,
        "app_version": request.app.state.settings.app_version,
        "language": language,
        "a": account_copy_for(language),
        "current_user": request.session.get("user_id"),
        "language_urls": {
            "en": language_switch_url(request, "en"),
            "hu": language_switch_url(request, "hu"),
        },
        "csrf_token": csrf_token(request),
    }
    base.update(context)
    return cast(
        Response,
        request.app.state.templates.TemplateResponse(request=request, name=template, context=base),
    )


def _admin_user(request: Request, session: Session, settings: Settings) -> User:
    user = current_user(request, session, settings)
    if user is None:
        raise HTTPException(status_code=401)
    if user.email.casefold() not in settings.admin_email_allowlist:
        raise HTTPException(status_code=404)
    return user


def _step_up_is_valid(request: Request, user: User, settings: Settings) -> bool:
    email = request.session.get("admin_verified_email")
    verified_at = request.session.get("admin_verified_at")
    return (
        email == user.email.casefold()
        and isinstance(verified_at, (int, float))
        and time.time() - verified_at <= settings.admin_session_max_age_seconds
    )


@router.get("", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    user = _admin_user(request, session, settings)
    if not _step_up_is_valid(request, user, settings):
        return _render(request, "admin_access.html", {"sent": False, "error": None})
    snapshot = dashboard_snapshot(session)
    snapshot["health"] = {
        "application": "ok",
        "database": "ok",
        "search": "configured",
    }
    logger.info("Admin dashboard viewed")
    return _render(request, "admin_dashboard.html", {"dashboard": snapshot})


@router.post("/access", response_class=HTMLResponse)
def request_admin_access(
    request: Request,
    csrf: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    require_csrf(request, csrf)
    user = _admin_user(request, session, settings)
    limiter = cast(AuthRateLimiter, request.app.state.auth_rate_limiter)
    key = f"admin-access:{user.id}"
    if not limiter.allow(key):
        return _render(
            request,
            "admin_access.html",
            {"sent": False, "error": "Too many requests. Please try again later."},
        )
    token = create_admin_token(user.email, settings)
    language = language_from_request(request)
    url = f"{str(settings.public_base_url).rstrip('/')}/admin/verify?token={token}&lang={language}"
    sender = cast(AccountEmailSender, request.app.state.account_email_sender)
    try:
        sender.send_admin_access(user.email, url, language)
    except EmailDeliveryError:
        return _render(
            request,
            "admin_access.html",
            {"sent": False, "error": "Admin access email could not be sent."},
        )
    development_url = url if settings.app_env != "production" else None
    logger.info("Admin step-up email requested")
    return _render(
        request,
        "admin_access.html",
        {"sent": True, "error": None, "development_url": development_url},
    )


@router.get("/verify")
def verify_admin_access(
    request: Request,
    token: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    user = _admin_user(request, session, settings)
    email = verify_admin_token(token, settings)
    if email is None or email != user.email.casefold():
        raise HTTPException(status_code=400)
    request.session["admin_verified_email"] = email
    request.session["admin_verified_at"] = time.time()
    logger.info("Admin step-up verification completed")
    return RedirectResponse("/admin", status_code=303)

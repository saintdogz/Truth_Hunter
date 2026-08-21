"""Session-bound CSRF helpers for Phase 3 forms."""

import hmac
import secrets

from fastapi import HTTPException, Request, status


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not isinstance(token, str):
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def require_csrf(request: Request, supplied_token: str) -> None:
    expected = request.session.get("csrf_token")
    if not isinstance(expected, str) or not hmac.compare_digest(expected, supplied_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")

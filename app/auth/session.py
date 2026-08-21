"""Signed-session identity helpers."""

import secrets

from fastapi import Request
from sqlalchemy.orm import Session

from app.auth.service import AccountService
from app.core.config import Settings
from app.db.models import User


def guest_session_id(request: Request) -> str:
    value = request.session.get("guest_session_id")
    if not isinstance(value, str):
        value = secrets.token_urlsafe(32)
        request.session["guest_session_id"] = value
    return value


def current_user(request: Request, session: Session, settings: Settings) -> User | None:
    user_id = request.session.get("user_id")
    version = request.session.get("session_version")
    if not isinstance(user_id, str) or not isinstance(version, int):
        return None
    user = AccountService(session, settings).get_session_user(user_id, version)
    if user is None:
        request.session.pop("user_id", None)
        request.session.pop("session_version", None)
    return user


def sign_in(request: Request, user: User) -> None:
    csrf = request.session.get("csrf_token")
    guest_id = request.session.get("guest_session_id")
    language = request.session.get("language")
    request.session.clear()
    if isinstance(csrf, str):
        request.session["csrf_token"] = csrf
    if isinstance(guest_id, str):
        request.session["guest_session_id"] = guest_id
    if language in {"en", "hu"}:
        request.session["language"] = language
    request.session["user_id"] = str(user.id)
    request.session["session_version"] = user.session_version


def sign_out(request: Request) -> None:
    language = request.session.get("language")
    request.session.clear()
    if language in {"en", "hu"}:
        request.session["language"] = language

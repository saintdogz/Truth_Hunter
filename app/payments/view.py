"""Small payment context shared by server-rendered layouts."""

from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import User
from app.db.session import get_engine
from app.payments.access import monetization_allowed
from app.payments.service import MonetizationService


def payment_context(request: Request) -> dict[str, object]:
    settings: Settings = request.app.state.settings
    if not settings.monetization_enabled and not settings.owner_payment_testing_enabled:
        return {"show_monetization": False, "credit_balance": None}
    user_id = request.session.get("user_id")
    if not isinstance(user_id, str):
        return {"show_monetization": False, "credit_balance": None}
    try:
        parsed = UUID(user_id)
    except ValueError:
        return {"show_monetization": False, "credit_balance": None}
    with Session(get_engine()) as session:
        user = session.get(User, parsed)
        if user is None or user.deleted_at is not None:
            return {"show_monetization": False, "credit_balance": None}
        allowed = monetization_allowed(user, settings)
        return {
            "show_monetization": allowed,
            "credit_balance": MonetizationService(session, settings).balance(user)
            if allowed
            else None,
        }

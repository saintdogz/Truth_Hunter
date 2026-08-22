"""Single activation gate for public and allowlisted owner monetization."""

from app.core.config import Settings
from app.db.models import User


def monetization_allowed(user: User | None, settings: Settings) -> bool:
    if settings.monetization_enabled:
        return True
    return bool(
        user
        and settings.owner_payment_testing_enabled
        and user.email.lower() in settings.payment_owner_email_set
    )

"""Short-lived email step-up authentication for administrators."""

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import Settings

ADMIN_SALT = "truth-hunter-admin-access-v1"


def create_admin_token(email: str, settings: Settings) -> str:
    signer = URLSafeTimedSerializer(settings.app_secret.get_secret_value(), salt=ADMIN_SALT)
    return str(signer.dumps({"email": email.casefold(), "purpose": "admin_access"}))


def verify_admin_token(token: str, settings: Settings) -> str | None:
    signer = URLSafeTimedSerializer(settings.app_secret.get_secret_value(), salt=ADMIN_SALT)
    try:
        payload = signer.loads(token, max_age=settings.admin_access_max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict) or payload.get("purpose") != "admin_access":
        return None
    email = payload.get("email")
    if not isinstance(email, str) or email not in settings.admin_email_allowlist:
        return None
    return email

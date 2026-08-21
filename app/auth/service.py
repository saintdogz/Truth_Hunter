"""Account lifecycle, credential validation, signed tokens, and ownership operations."""

import hashlib
import re
from datetime import datetime, timezone
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Investigation, User

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class AccountError(ValueError):
    pass


class InvalidTokenError(AccountError):
    pass


class AuthenticationError(AccountError):
    pass


LOGIN_FAILURE_MESSAGE = (
    "We couldn't sign you in. Check your email and password. "
    "If the account was deleted, register again."
)


class AccountService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._hasher = PasswordHasher()
        self._serializer = URLSafeTimedSerializer(
            settings.app_secret.get_secret_value(), salt="truth-hunter-accounts-v1"
        )

    @staticmethod
    def normalize_email(email: str) -> str:
        normalized = email.strip().lower()
        if len(normalized) > 320 or not EMAIL_PATTERN.fullmatch(normalized):
            raise AccountError("Enter a valid email address.")
        return normalized

    @staticmethod
    def validate_password(password: str) -> None:
        if len(password) < 12 or len(password) > 256:
            raise AccountError("Password must contain between 12 and 256 characters.")

    def register(self, email: str, password: str) -> User:
        normalized = self.normalize_email(email)
        self.validate_password(password)
        existing = self._session.scalar(select(User).where(User.email == normalized))
        if existing is not None and existing.deleted_at is None:
            raise AccountError("An account with this email already exists.")
        if existing is not None:
            raise AccountError("This email cannot currently be registered.")
        user = User(email=normalized, password_hash=self._hasher.hash(password))
        self._session.add(user)
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise AccountError("An account with this email already exists.") from exc
        self._session.refresh(user)
        return user

    def authenticate(self, email: str, password: str) -> User:
        try:
            normalized = self.normalize_email(email)
        except AccountError as exc:
            raise AuthenticationError(LOGIN_FAILURE_MESSAGE) from exc
        user = self._session.scalar(select(User).where(User.email == normalized))
        if user is None or user.deleted_at is not None or user.password_hash is None:
            raise AuthenticationError(LOGIN_FAILURE_MESSAGE)
        try:
            valid = self._hasher.verify(user.password_hash, password)
        except (VerifyMismatchError, InvalidHashError) as exc:
            raise AuthenticationError(LOGIN_FAILURE_MESSAGE) from exc
        if not valid:
            raise AuthenticationError(LOGIN_FAILURE_MESSAGE)
        if not user.email_verified:
            raise AuthenticationError("Verify your email before signing in.")
        if self._hasher.check_needs_rehash(user.password_hash):
            user.password_hash = self._hasher.hash(password)
            self._session.commit()
        return user

    def verification_token(self, user: User) -> str:
        return self._serializer.dumps({"purpose": "verify", "uid": str(user.id)})

    def verify_email(self, token: str) -> User:
        payload = self._load_token(token, "verify", self._settings.email_token_max_age_seconds)
        user = self._active_user(payload["uid"])
        user.email_verified = True
        self._session.commit()
        return user

    def password_reset_token(self, user: User) -> str:
        return self._serializer.dumps(
            {
                "purpose": "reset",
                "uid": str(user.id),
                "fingerprint": self._password_fingerprint(user),
            }
        )

    def find_active_user(self, email: str) -> User | None:
        try:
            normalized = self.normalize_email(email)
        except AccountError:
            return None
        return self._session.scalar(
            select(User).where(User.email == normalized, User.deleted_at.is_(None))
        )

    def discard_unverified_registration(self, user: User) -> None:
        if user.email_verified:
            return
        self._session.delete(user)
        self._session.commit()

    def reset_password(self, token: str, password: str) -> User:
        self.validate_password(password)
        payload = self._load_token(token, "reset", self._settings.reset_token_max_age_seconds)
        user = self._active_user(payload["uid"])
        if payload.get("fingerprint") != self._password_fingerprint(user):
            raise InvalidTokenError("This password-reset link is no longer valid.")
        user.password_hash = self._hasher.hash(password)
        user.session_version += 1
        self._session.commit()
        return user

    def get_session_user(self, user_id: str, session_version: int) -> User | None:
        try:
            parsed_id = UUID(user_id)
        except ValueError:
            return None
        return self._session.scalar(
            select(User).where(
                User.id == parsed_id,
                User.deleted_at.is_(None),
                User.email_verified.is_(True),
                User.session_version == session_version,
            )
        )

    def claim_guest_investigations(self, user: User, session_id: str | None) -> int:
        if not session_id:
            return 0
        investigation_ids = list(
            self._session.scalars(
                select(Investigation.id).where(
                    Investigation.session_id == session_id, Investigation.user_id.is_(None)
                )
            )
        )
        self._session.execute(
            update(Investigation)
            .where(Investigation.session_id == session_id, Investigation.user_id.is_(None))
            .values(user_id=user.id, session_id=None)
        )
        self._session.commit()
        return len(investigation_ids)

    def history(self, user: User) -> list[Investigation]:
        return list(
            self._session.scalars(
                select(Investigation)
                .where(Investigation.user_id == user.id)
                .order_by(Investigation.created_at.desc())
            )
        )

    def delete_account(self, user: User) -> None:
        self._session.execute(delete(Investigation).where(Investigation.user_id == user.id))
        user.email = f"deleted-{user.id}@invalid.local"
        user.password_hash = None
        user.google_subject = None
        user.email_verified = False
        user.session_version += 1
        user.deleted_at = datetime.now(timezone.utc)
        self._session.commit()

    def _active_user(self, user_id: str) -> User:
        try:
            parsed_id = UUID(user_id)
        except ValueError as exc:
            raise InvalidTokenError("This account link is invalid.") from exc
        user = self._session.get(User, parsed_id)
        if user is None or user.deleted_at is not None:
            raise InvalidTokenError("This account link is invalid.")
        return user

    def _load_token(self, token: str, purpose: str, max_age: int) -> dict[str, str]:
        try:
            payload = self._serializer.loads(token, max_age=max_age)
        except (BadSignature, SignatureExpired) as exc:
            raise InvalidTokenError("This account link is invalid or expired.") from exc
        if not isinstance(payload, dict) or payload.get("purpose") != purpose:
            raise InvalidTokenError("This account link is invalid or expired.")
        uid = payload.get("uid")
        if not isinstance(uid, str):
            raise InvalidTokenError("This account link is invalid or expired.")
        return {str(key): str(value) for key, value in payload.items()}

    @staticmethod
    def _password_fingerprint(user: User) -> str:
        value = user.password_hash or "no-password"
        return hashlib.sha256(value.encode()).hexdigest()[:24]

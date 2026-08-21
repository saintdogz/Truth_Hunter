"""Deterministic Phase 4 account service tests."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.service import AccountService, AuthenticationError, InvalidTokenError
from app.core.config import Settings
from app.db.base import Base
from app.db.models import Investigation


def account_settings() -> Settings:
    return Settings(
        app_env="test",
        app_secret="account-test-secret",
        database_url="postgresql+psycopg://test:test@localhost/test",
    )


def account_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def test_registration_verification_and_login() -> None:
    with account_session() as session:
        service = AccountService(session, account_settings())
        user = service.register(" Person@Example.COM ", "correct horse battery staple")

        assert user.email == "person@example.com"
        assert user.password_hash is not None
        assert user.password_hash.startswith("$argon2id$")
        try:
            service.authenticate(user.email, "correct horse battery staple")
        except AuthenticationError as exc:
            assert "Verify" in str(exc)
        else:
            raise AssertionError("Unverified account was allowed to sign in")

        verified = service.verify_email(service.verification_token(user))
        authenticated = service.authenticate(user.email, "correct horse battery staple")

        assert verified.email_verified is True
        assert authenticated.id == user.id


def test_password_reset_is_single_use_and_revokes_sessions() -> None:
    with account_session() as session:
        service = AccountService(session, account_settings())
        user = service.register("person@example.com", "correct horse battery staple")
        service.verify_email(service.verification_token(user))
        token = service.password_reset_token(user)
        old_version = user.session_version

        service.reset_password(token, "a completely different secure password")

        assert user.session_version == old_version + 1
        assert service.authenticate(user.email, "a completely different secure password")
        try:
            service.reset_password(token, "another completely different password")
        except InvalidTokenError:
            pass
        else:
            raise AssertionError("Password reset token was reusable")


def test_login_failure_does_not_reveal_whether_account_exists() -> None:
    with account_session() as session:
        service = AccountService(session, account_settings())
        user = service.register("person@example.com", "correct horse battery staple")
        service.verify_email(service.verification_token(user))

        messages = []
        for email, password in (
            ("missing@example.com", "correct horse battery staple"),
            ("person@example.com", "incorrect but sufficiently long password"),
        ):
            try:
                service.authenticate(email, password)
            except AuthenticationError as exc:
                messages.append(str(exc))

        assert len(messages) == 2
        assert messages[0] == messages[1]
        assert "deleted" in messages[0]


def test_guest_investigation_claim_and_account_deletion() -> None:
    with account_session() as session:
        service = AccountService(session, account_settings())
        user = service.register("person@example.com", "correct horse battery staple")
        investigation = Investigation(
            original_claim="A test claim",
            status="COMPLETED",
            session_id="guest-session",
        )
        session.add(investigation)
        session.commit()

        assert service.claim_guest_investigations(user, "guest-session") == 1
        assert service.history(user)[0].id == investigation.id

        service.delete_account(user)

        assert user.deleted_at is not None
        assert user.password_hash is None
        assert service.history(user) == []

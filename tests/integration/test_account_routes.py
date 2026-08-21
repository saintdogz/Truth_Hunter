"""Server-rendered account lifecycle integration tests."""

import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.routes import _development_email_url
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app


def csrf_from(text: str) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', text)
    assert match is not None
    return match.group(1)


def test_real_email_delivery_never_exposes_account_token() -> None:
    settings = Settings(
        app_env="development",
        app_secret="account-route-test-secret",
        database_url="postgresql+psycopg://test:test@localhost/test",
        email_delivery_mode="resend",
        resend_api_key="resend-test-key",
        resend_from_email="Truth Hunter <accounts@example.com>",
    )

    assert _development_email_url(settings, "https://example.com/verify?token=secret") is None


@pytest.fixture
def account_client() -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        app_secret="account-route-test-secret",
        app_trusted_hosts="testserver",
        database_url="postgresql+psycopg://test:test@localhost/test",
        email_delivery_mode="development",
        public_base_url="http://testserver",
    )
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def session_override() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app = create_app(settings)
    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        yield client


def test_register_verify_history_logout_and_login(account_client: TestClient) -> None:
    register_page = account_client.get("/register")
    registered = account_client.post(
        "/register",
        data={
            "email": "person@example.com",
            "password": "correct horse battery staple",
            "csrf": csrf_from(register_page.text),
        },
    )

    assert registered.status_code == 201
    match = re.search(r'href="([^"]*verify-email\?token=[^"]+)"', registered.text)
    assert match is not None

    verified = account_client.get(match.group(1), follow_redirects=False)
    assert verified.status_code == 303
    assert verified.headers["location"] == "/history"
    history = account_client.get("/history")
    assert history.status_code == 200
    assert "Investigation history" in history.text

    account = account_client.get("/account")
    logged_out = account_client.post(
        "/logout", data={"csrf": csrf_from(account.text)}, follow_redirects=False
    )
    assert logged_out.status_code == 303
    assert account_client.get("/history", follow_redirects=False).headers["location"] == "/login"

    login_page = account_client.get("/login")
    logged_in = account_client.post(
        "/login",
        data={
            "email": "person@example.com",
            "password": "correct horse battery staple",
            "csrf": csrf_from(login_page.text),
        },
        follow_redirects=False,
    )
    assert logged_in.status_code == 303
    assert logged_in.headers["location"] == "/history"


def test_registration_requires_csrf_and_strong_password(account_client: TestClient) -> None:
    assert (
        account_client.post(
            "/register",
            data={"email": "person@example.com", "password": "short", "csrf": "wrong"},
        ).status_code
        == 403
    )
    page = account_client.get("/register")
    weak = account_client.post(
        "/register",
        data={
            "email": "person@example.com",
            "password": "short",
            "csrf": csrf_from(page.text),
        },
    )
    assert weak.status_code == 400
    assert "between 12 and 256" in weak.text


def test_forgot_password_does_not_enumerate_accounts(account_client: TestClient) -> None:
    page = account_client.get("/forgot-password")
    response = account_client.post(
        "/forgot-password",
        data={"email": "missing@example.com", "csrf": csrf_from(page.text)},
    )
    assert response.status_code == 200
    assert "If the account exists" in response.text


def test_hungarian_account_copy_and_language_persist(account_client: TestClient) -> None:
    register_page = account_client.get("/register?lang=hu")

    assert register_page.status_code == 200
    assert 'lang="hu"' in register_page.text
    assert "Fiók létrehozása" in register_page.text
    assert "Bejelentkezés" in register_page.text

    weak = account_client.post(
        "/register",
        data={
            "email": "person@example.com",
            "password": "short",
            "csrf": csrf_from(register_page.text),
        },
    )

    assert weak.status_code == 400
    assert "A jelszónak 12–256 karakterből kell állnia." in weak.text
    assert "Fiók létrehozása" in weak.text


def test_hungarian_reset_request_is_non_enumerating(account_client: TestClient) -> None:
    page = account_client.get("/forgot-password?lang=hu")
    response = account_client.post(
        "/forgot-password",
        data={"email": "missing@example.com", "csrf": csrf_from(page.text)},
    )

    assert response.status_code == 200
    assert "Ha a fiók létezik" in response.text
    assert "A kérést fogadtuk" in response.text


def test_language_switch_preserves_account_token(account_client: TestClient) -> None:
    response = account_client.get("/reset-password?token=signed-token&lang=hu")

    assert response.status_code == 200
    assert "/reset-password?token=signed-token&amp;lang=en" in response.text
    assert "/reset-password?token=signed-token&amp;lang=hu" in response.text

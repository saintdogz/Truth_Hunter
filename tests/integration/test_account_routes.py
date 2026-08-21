"""Server-rendered account lifecycle integration tests."""

import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app


def csrf_from(text: str) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', text)
    assert match is not None
    return match.group(1)


@pytest.fixture
def account_client() -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        app_secret="account-route-test-secret",
        app_trusted_hosts="testserver",
        database_url="postgresql+psycopg://test:test@localhost/test",
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

"""Private operations dashboard and email step-up integration tests."""

import re
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.models import Feedback, Investigation
from app.db.session import get_session
from app.main import create_app


def csrf_from(text: str) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', text)
    assert match is not None
    return match.group(1)


@pytest.fixture
def admin_client() -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        app_secret="admin-dashboard-test-secret",
        app_trusted_hosts="testserver",
        database_url="postgresql+psycopg://test:test@localhost/test",
        email_delivery_mode="development",
        public_base_url="http://testserver",
        admin_emails="admin@example.com",
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


def register_and_verify(client: TestClient, email: str) -> None:
    page = client.get("/register")
    registered = client.post(
        "/register",
        data={
            "email": email,
            "password": "correct horse battery staple",
            "csrf": csrf_from(page.text),
        },
    )
    match = re.search(r'href="([^"]*verify-email\?token=[^"]+)"', registered.text)
    assert match is not None
    assert client.get(match.group(1), follow_redirects=False).status_code == 303


def unlock_admin(client: TestClient) -> None:
    access = client.get("/admin")
    sent = client.post("/admin/access", data={"csrf": csrf_from(access.text)})
    match = re.search(r'href="([^"]*/admin/verify\?token=[^"]+)"', sent.text)
    assert match is not None
    verified = client.get(match.group(1), follow_redirects=False)
    assert verified.status_code == 303
    assert verified.headers["location"] == "/admin"


def test_admin_requires_allowlist_and_email_step_up(admin_client: TestClient) -> None:
    register_and_verify(admin_client, "admin@example.com")
    access = admin_client.get("/admin")
    assert access.status_code == 200
    assert "Confirm it’s you" in access.text
    unlock_admin(admin_client)

    dashboard = admin_client.get("/admin")
    assert dashboard.status_code == 200
    assert "Operations" in dashboard.text
    assert "Raw claims, user identities" in dashboard.text
    assert "Registered users" in dashboard.text
    assert "Email verified" in dashboard.text
    assert "admin@example.com" not in dashboard.text


def test_non_admin_receives_not_found(admin_client: TestClient) -> None:
    register_and_verify(admin_client, "person@example.com")
    assert admin_client.get("/admin").status_code == 404


def test_dashboard_aggregates_provider_fallbacks(admin_client: TestClient) -> None:
    register_and_verify(admin_client, "admin@example.com")
    app = cast(FastAPI, admin_client.app)
    session_dependency = app.dependency_overrides[get_session]
    generator = session_dependency()
    session = next(generator)
    now = datetime.now(timezone.utc)
    investigation = Investigation(
        original_claim="sensitive claim intentionally absent from dashboard",
        status="COMPLETED",
        verdict="TRUE",
        language="en",
        source_count=4,
        ai_model="gemini/test",
        created_at=now - timedelta(seconds=45),
        completed_at=now,
        ai_provider_attempts=[
            {
                "provider": "groq",
                "status": "failed",
                "category": "rate_limit",
                "tier": "free",
            },
            {"provider": "gemini", "status": "succeeded", "tier": "free"},
        ],
    )
    session.add(investigation)
    session.flush()
    session.add(
        Feedback(
            investigation_id=investigation.id,
            session_id="feedback-test-session",
            value="HELPFUL",
        )
    )
    session.commit()
    generator.close()

    unlock_admin(admin_client)
    dashboard = admin_client.get("/admin")
    assert "rate limit" in dashboard.text
    assert "gemini" in dashboard.text
    assert "Helpful results" in dashboard.text
    assert "1 helpful" in dashboard.text
    assert "sensitive claim" not in dashboard.text

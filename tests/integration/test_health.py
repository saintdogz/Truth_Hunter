"""Health endpoint tests."""

from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.web.routes import get_readiness_checker


def test_liveness_does_not_call_database(client: TestClient) -> None:
    def unexpected_database_call() -> bool:
        raise AssertionError("liveness must not depend on PostgreSQL")

    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_readiness_checker] = lambda: unexpected_database_call
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_readiness_reports_available_database(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_readiness_checker] = lambda: lambda: True

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ok"}


def test_readiness_sanitizes_database_failure(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_readiness_checker] = lambda: lambda: False

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "version": "0.1.0",
        "checks": {"database": "unavailable"},
    }
    assert "postgresql" not in response.text.lower()

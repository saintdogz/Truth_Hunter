"""Shared Phase 1 test fixtures."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        app_secret="test-only-secret",
        app_trusted_hosts="testserver,localhost",
        public_rate_limits_enabled=False,
        database_url=("postgresql+psycopg://truthhunter:test-only@localhost:5432/truthhunter_test"),
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client

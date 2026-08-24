"""Server-rendered application behavior tests."""

from fastapi.testclient import TestClient
from pydantic import AnyHttpUrl

from app.core.config import Settings
from app.main import create_app


def test_home_is_branded_claim_landing_page(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "TRUTH" in response.text
    assert "HUNTER" in response.text
    assert "Don&#39;t believe it. Investigate it." in response.text
    assert "v0.1.0" in response.text
    assert '<form method="post" action="/investigations"' in response.text
    assert 'enctype="multipart/form-data"' in response.text
    assert 'maxlength="500"' in response.text
    assert 'accept="image/jpeg,image/png,image/webp"' in response.text


def test_home_supports_hungarian_interface(client: TestClient) -> None:
    response = client.get("/?lang=hu")

    assert response.status_code == 200
    assert "Ne hidd el. Vizsgáld meg." in response.text


def test_support_link_is_hidden_when_not_configured(client: TestClient) -> None:
    response = client.get("/")

    assert "Support Truth Hunter" not in response.text


def test_configured_support_link_is_safe_and_visible(settings: Settings) -> None:
    settings.support_url = AnyHttpUrl("https://support.example.com/truth-hunter")
    with TestClient(create_app(settings)) as support_client:
        response = support_client.get("/")

    assert 'href="https://support.example.com/truth-hunter"' in response.text
    assert 'target="_blank" rel="noopener noreferrer"' in response.text


def test_static_stylesheet_is_served(client: TestClient) -> None:
    response = client.get("/static/css/app.css")

    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


def test_custom_not_found_page(client: TestClient) -> None:
    response = client.get("/not-a-real-page")

    assert response.status_code == 404
    assert "Page not found" in response.text
    assert "Traceback" not in response.text


def test_security_headers_are_present(client: TestClient) -> None:
    response = client.get("/")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"

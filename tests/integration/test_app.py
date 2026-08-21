"""Server-rendered application behavior tests."""

from fastapi.testclient import TestClient


def test_home_is_branded_placeholder(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "TRUTH" in response.text
    assert "HUNTER" in response.text
    assert "Don't believe it. Investigate it." in response.text
    assert "v0.1.0" in response.text
    assert "<form" not in response.text


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

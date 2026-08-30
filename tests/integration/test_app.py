"""Server-rendered application behavior tests."""

from fastapi.testclient import TestClient
from pydantic import AnyHttpUrl, SecretStr

from app.core.config import Settings
from app.main import create_app


def test_home_is_branded_claim_landing_page(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "TRUTH" in response.text
    assert "HUNTER" in response.text
    assert "Don&#39;t believe it. Investigate it." in response.text
    assert "v0.9.0-rc2" in response.text
    assert '<form method="post" action="/investigations"' in response.text
    assert 'enctype="multipart/form-data"' in response.text
    assert 'maxlength="500"' in response.text
    assert 'accept="image/jpeg,image/png,image/webp"' in response.text
    assert "Ctrl+V" in response.text
    assert 'id="image-preview"' in response.text
    assert 'src="http://testserver/static/js/claim-input.js?v=' in response.text
    assert 'href="http://testserver/static/css/app.css?v=' in response.text
    assert "Not sure where to start? Try a real claim." in response.text
    assert response.text.count('class="example-category"') == 3
    assert response.text.count("Try this claim") == 2
    assert "Stúdióban készültek a holdra szállás felvételei?" in response.text
    assert "Állítás kipróbálása" in response.text
    assert 'data-example="A Holdra szállás felvételeit egy stúdióban készítették."' in response.text
    assert '<span aria-hidden="true">03</span>' not in response.text


def test_home_supports_hungarian_interface(client: TestClient) -> None:
    response = client.get("/?lang=hu")

    assert response.status_code == 200
    assert "Ne hidd el. Vizsgáld meg." in response.text
    assert "Nem tudod, mivel kezdd?" in response.text


def test_about_page_explains_the_service_without_exposing_secrets(client: TestClient) -> None:
    response = client.get("/about")

    assert response.status_code == 200
    assert "How Truth Hunter works" in response.text
    assert "SearXNG" in response.text
    assert "AI does not choose a truth percentage" in response.text
    assert "Tesseract OCR" in response.text
    assert "test-only-secret" not in response.text


def test_about_page_supports_hungarian(client: TestClient) -> None:
    response = client.get("/about?lang=hu")

    assert response.status_code == 200
    assert "Hogyan működik a Truth Hunter?" in response.text
    assert "Fontos korlátok" in response.text


def test_bilingual_legal_pages_and_footer_links_are_public(client: TestClient) -> None:
    privacy = client.get("/privacy")
    terms_hu = client.get("/terms?lang=hu")
    registration = client.get("/register")

    assert privacy.status_code == 200
    assert "Privacy Policy" in privacy.text
    assert "Uploaded images are discarded after OCR" in privacy.text
    assert terms_hu.status_code == 200
    assert "Felhasználási feltételek" in terms_hu.text
    assert 'href="/privacy?lang=en"' in privacy.text
    assert 'href="/terms?lang=hu"' in registration.text


def test_support_link_is_hidden_when_not_configured(client: TestClient) -> None:
    response = client.get("/")

    assert "Support Truth Hunter" not in response.text
    assert "Discord: saintdogz" in response.text


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


def test_clipboard_image_script_is_served(client: TestClient) -> None:
    response = client.get("/static/js/claim-input.js")

    assert response.status_code == 200
    assert "DataTransfer" in response.text
    assert 'document.addEventListener("paste"' in response.text


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
    csp = response.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "https://challenges.cloudflare.com" in csp
    assert "strict-transport-security" not in response.headers


def test_production_enables_hsts(settings: Settings) -> None:
    settings.app_env = "production"
    settings.email_delivery_mode = "resend"
    settings.resend_api_key = SecretStr("test-resend-key")
    settings.resend_from_email = "accounts@example.test"
    production_app = create_app(settings)
    production_app.state.investigation_service.recover_interrupted = lambda: 0
    with TestClient(production_app) as production_client:
        response = production_client.get("/")

    assert response.headers["strict-transport-security"] == ("max-age=31536000; includeSubDomains")

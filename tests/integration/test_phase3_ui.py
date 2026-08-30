"""Phase 3 server-rendered investigation flow tests."""

import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.db.models import EvidenceRecord, Investigation, Source
from app.investigation.models import ClaimInterpretation, ClaimType
from app.investigation.repository import InvestigationNotFoundError
from app.web.service import InvestigationWebService


class FakeWebService:
    def __init__(self) -> None:
        self.items: dict[UUID, Investigation] = {}
        self.investigate_calls: list[tuple[UUID, str, bool]] = []

    async def interpret(
        self,
        original_claim: str,
        *,
        user_id: UUID | None = None,
        session_id: str | None = None,
    ) -> tuple[UUID, ClaimInterpretation]:
        investigation_id = uuid4()
        investigation = Investigation(
            id=investigation_id,
            original_claim=original_claim,
            interpreted_claim="The normalized proposition.",
            language="en",
            claim_type="factual",
            correction_used=False,
            status="AWAITING_CONFIRMATION",
            pro_arguments=[],
            contra_arguments=[],
            conflicting_source_ids=[],
            search_languages=[],
            user_id=user_id,
            session_id=session_id,
        )
        self.items[investigation_id] = investigation
        return investigation_id, ClaimInterpretation(
            interpreted_claim=investigation.interpreted_claim,
            language="en",
            claim_type=ClaimType.FACTUAL,
            confidence=0.9,
        )

    async def investigate(
        self, investigation_id: UUID, confirmed_claim: str, *, corrected: bool
    ) -> None:
        self.investigate_calls.append((investigation_id, confirmed_claim, corrected))
        self.items[investigation_id].status = "SEARCHING"

    def get(self, investigation_id: UUID) -> Investigation:
        return self.items[investigation_id]

    def get_public(self, public_slug: str) -> Investigation:
        for item in self.items.values():
            if item.is_public and item.public_slug == public_slug:
                return item
        raise InvestigationNotFoundError(public_slug)


def csrf_from(response_text: str) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', response_text)
    assert match is not None
    return match.group(1)


def install_fake(client: TestClient) -> FakeWebService:
    fake = FakeWebService()
    client.app.state.investigation_service = fake  # type: ignore[attr-defined]
    return fake


def test_claim_submission_requires_csrf(client: TestClient) -> None:
    install_fake(client)
    response = client.post("/investigations", data={"claim": "A valid claim", "csrf": "invalid"})

    assert response.status_code == 403


def test_claim_submission_rejects_failed_turnstile(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install_fake(client)
    settings.turnstile_site_key = "1x00000000000000000000AA"
    settings.turnstile_secret_key = SecretStr("1x0000000000000000000000000000000AA")

    async def reject_challenge(*_args: object, **_kwargs: object) -> bool:
        return False

    monkeypatch.setattr("app.web.routes.verify_turnstile", reject_challenge)
    home = client.get("/")
    assert "challenges.cloudflare.com/turnstile/v0/api.js" in home.text
    response = client.post(
        "/investigations",
        data={"claim": "A valid claim", "csrf": csrf_from(home.text)},
    )

    assert response.status_code == 400
    assert "security check" in response.text
    assert not fake.items


def test_claim_submission_returns_localized_rate_limit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install_fake(client)
    monkeypatch.setattr("app.web.routes.consume_public_limit", lambda *_args, **_kwargs: False)
    home = client.get("/")
    response = client.post(
        "/investigations",
        data={"claim": "A valid claim", "csrf": csrf_from(home.text)},
    )

    assert response.status_code == 429
    assert "temporary usage limit" in response.text
    assert not fake.items


def test_submission_redirects_to_escaped_confirmation(client: TestClient) -> None:
    fake = install_fake(client)
    home = client.get("/")
    claim = '<script>alert("xss")</script> The claim remains data.'
    submitted = client.post(
        "/investigations",
        data={"claim": claim, "csrf": csrf_from(home.text)},
        follow_redirects=False,
    )

    assert submitted.status_code == 303
    confirmation = client.get(submitted.headers["location"])
    assert confirmation.status_code == 200
    assert "&lt;script&gt;" in confirmation.text
    assert claim not in confirmation.text
    assert len(fake.items) == 1


def test_image_text_enters_existing_confirmation_flow(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install_fake(client)
    extracted = "Roger Penrose says the Big Bang ended a previous universe."
    monkeypatch.setattr("app.web.routes.extract_image_text", lambda *_args, **_kwargs: extracted)
    home = client.get("/")

    submitted = client.post(
        "/investigations",
        data={"csrf": csrf_from(home.text)},
        files={"image": ("claim.jpg", b"bounded-image-bytes", "image/jpeg")},
        follow_redirects=False,
    )

    assert submitted.status_code == 303
    investigation = next(iter(fake.items.values()))
    assert investigation.original_claim == extracted
    confirmation = client.get(submitted.headers["location"])
    assert confirmation.status_code == 200
    assert extracted in confirmation.text


def test_submission_rejects_text_and_image_together(client: TestClient) -> None:
    install_fake(client)
    home = client.get("/")

    response = client.post(
        "/investigations",
        data={"claim": "A typed claim", "csrf": csrf_from(home.text)},
        files={"image": ("claim.png", b"image", "image/png")},
    )

    assert response.status_code == 400
    assert "not both" in response.text


def test_single_correction_is_forwarded_to_background_service(client: TestClient) -> None:
    fake = install_fake(client)
    home = client.get("/")
    submitted = client.post(
        "/investigations",
        data={"claim": "Original claim", "csrf": csrf_from(home.text)},
        follow_redirects=False,
    )
    confirmation = client.get(submitted.headers["location"])
    investigation_id = next(iter(fake.items))
    corrected = "A precise corrected proposition."

    response = client.post(
        f"/investigations/{investigation_id}/confirm",
        data={
            "action": "correct",
            "corrected_claim": corrected,
            "csrf": csrf_from(confirmation.text),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert fake.investigate_calls == [(investigation_id, corrected, True)]


def test_progress_status_is_localized(client: TestClient) -> None:
    fake = install_fake(client)
    investigation_id = uuid4()
    fake.items[investigation_id] = Investigation(
        id=investigation_id,
        original_claim="Eredeti állítás",
        interpreted_claim="Értelmezett állítás",
        language="hu",
        claim_type="factual",
        status="EVALUATING_EVIDENCE",
    )

    response = client.get(f"/investigations/{investigation_id}/status")

    assert response.status_code == 200
    assert response.json()["label"] == "Bizonyítékok értékelése"
    assert response.json()["stage_index"] == 3
    assert response.json()["stage_total"] == 5
    assert response.json()["result_url"] is None

    progress = client.get(f"/investigations/{investigation_id}/progress")
    assert progress.status_code == 200
    assert "Keresés" in progress.text
    assert "Gyűjtés" in progress.text
    assert 'aria-valuenow="3"' in progress.text

    fake.items[investigation_id].status = "SEARCH_FAILED"
    response = client.get(f"/investigations/{investigation_id}/status")

    assert response.status_code == 200
    assert response.json()["label"] == "A bizonyítékkeresés átmenetileg nem érhető el"
    assert response.json()["result_url"] is None


def test_result_exposes_bounded_evidence_details_during_testing(client: TestClient) -> None:
    fake = install_fake(client)
    investigation_id = uuid4()
    investigation = Investigation(
        id=investigation_id,
        original_claim="Original claim",
        interpreted_claim="Investigated claim",
        language="en",
        claim_type="factual",
        status="COMPLETED",
        verdict="MOSTLY_TRUE",
        supporting_score=72.0,
        contradicting_score=28.0,
        evidence_sufficient=True,
        confidence="HIGH",
        summary="The strongest available evidence supports the claim.",
        pro_arguments=["Primary evidence supports the central proposition."],
        contra_arguments=["One limitation remains."],
        conflict_detected=False,
        conflicting_source_ids=[],
        ai_model="test-model",
        prompt_version="phase2-prompts-v1",
        search_provider="searxng",
        search_languages=["en", "hu"],
        scoring_version="evidence-v1",
        source_count=1,
        is_public=True,
        public_slug="evidence-test-share",
        completed_at=datetime.now(timezone.utc),
    )
    source = Source(
        id=uuid4(),
        investigation_id=investigation_id,
        url="https://secret-source.example/evidence",
        title="Source title",
        domain="secret-source.example",
        source_type="PRIMARY_RESEARCH",
        quality_score=0.9,
        relevance_score=0.8,
        excerpt="A short relevant excerpt",
        extracted_text="Stored full source content must remain private",
    )
    evidence = EvidenceRecord(
        id=uuid4(),
        investigation_id=investigation_id,
        source_id=source.id,
        position="SUPPORTING",
        strength=0.85,
        relevance=0.8,
        quality=0.9,
        independence=0.7,
        recency=0.6,
        summary="The source directly supports the investigated claim.",
    )
    source.evidence = [evidence]
    investigation.sources = [source]
    investigation.evidence = [evidence]
    fake.items[investigation_id] = investigation

    response = client.get("/investigation/evidence-test-share")

    assert response.status_code == 200
    assert "Mostly True" in response.text
    assert 'class="result-deep-dive"' in response.text
    assert "Explore the evidence" in response.text
    assert 'class="result-claim"' in response.text
    assert "Why:" in response.text
    assert "1 relevant evidence item" in response.text
    assert "average quality was 90%" in response.text
    assert "72.0% PRO" in response.text
    assert 'href="https://secret-source.example/evidence"' in response.text
    assert "A short relevant excerpt" in response.text
    assert "The source directly supports the investigated claim." in response.text
    assert "Supporting" in response.text
    assert "85%" in response.text
    assert "Stored full source content must remain private" not in response.text
    assert "Public investigation" in response.text
    assert "Report this public result" in response.text

    investigation.evidence_sufficient = False
    insufficient = client.get("/investigation/evidence-test-share")
    assert "72.0% PRO" not in insufficient.text
    assert "precise percentages would be misleading" in insufficient.text


def test_owner_result_clearly_identifies_the_public_share_link(client: TestClient) -> None:
    fake = install_fake(client)
    home = client.get("/")
    client.post(
        "/investigations",
        data={"claim": "A shareable claim", "csrf": csrf_from(home.text)},
        follow_redirects=False,
    )
    investigation_id = next(iter(fake.items))
    investigation = fake.items[investigation_id]
    investigation.status = "COMPLETED"
    investigation.verdict = "INCONCLUSIVE"
    investigation.confidence = "LOW"
    investigation.is_public = True
    investigation.public_slug = "permanent-public-slug"

    response = client.get(f"/investigations/{investigation_id}/result?sharing=published")

    assert response.status_code == 200
    assert "Share the public link below" in response.text
    assert "not the private address in your browser" in response.text
    assert re.search(r'value="https?://[^\"]+/investigation/permanent-public-slug"', response.text)
    assert re.search(r'href="https?://[^\"]+/investigation/permanent-public-slug"', response.text)
    assert "Copy the public link shown below" in response.text


def test_shared_owner_url_redirects_visitors_to_public_slug(client: TestClient) -> None:
    fake = install_fake(client)
    home = client.get("/")
    client.post(
        "/investigations",
        data={"claim": "A shareable claim", "csrf": csrf_from(home.text)},
        follow_redirects=False,
    )
    investigation_id = next(iter(fake.items))
    investigation = fake.items[investigation_id]
    investigation.status = "COMPLETED"
    investigation.is_public = True
    investigation.public_slug = "visitor-public-slug"
    client.cookies.clear()

    response = client.get(
        f"/investigations/{investigation_id}/result?sharing=published",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/investigation/visitor-public-slug"


def test_result_service_eagerly_loads_nested_source_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    investigation_id = uuid4()
    source_id = uuid4()
    with Session(engine) as session:
        investigation = Investigation(
            id=investigation_id,
            original_claim="Detached snapshot test",
            status="COMPLETED",
        )
        source = Source(
            id=source_id,
            investigation_id=investigation_id,
            url="https://example.test/source",
            title="Test source",
            domain="example.test",
            extracted_text="Private retained text",
        )
        source.evidence = [
            EvidenceRecord(
                investigation_id=investigation_id,
                source_id=source_id,
                position="SUPPORTING",
                strength=0.8,
                relevance=0.8,
                quality=0.8,
                independence=0.8,
                recency=0.8,
                summary="Structured evidence",
            )
        ]
        investigation.sources = [source]
        session.add(investigation)
        session.commit()

    monkeypatch.setattr("app.web.service.get_engine", lambda: engine)
    loaded = InvestigationWebService(Settings(app_env="test")).get(investigation_id)

    assert loaded.sources[0].evidence[0].summary == "Structured evidence"


def test_private_result_uuid_is_not_visible_without_ownership(client: TestClient) -> None:
    fake = install_fake(client)
    investigation_id = uuid4()
    fake.items[investigation_id] = Investigation(
        id=investigation_id,
        original_claim="Private result",
        interpreted_claim="Private result",
        language="en",
        status="COMPLETED",
        verdict="INCONCLUSIVE",
        confidence="LOW",
        is_public=False,
    )

    response = client.get(f"/investigations/{investigation_id}/result")

    assert response.status_code == 404


def test_public_result_hides_owner_controls_and_feedback(client: TestClient) -> None:
    fake = install_fake(client)
    investigation_id = uuid4()
    fake.items[investigation_id] = Investigation(
        id=investigation_id,
        original_claim="Shared original claim",
        interpreted_claim="Shared interpreted claim",
        language="en",
        status="COMPLETED",
        verdict="INCONCLUSIVE",
        confidence="LOW",
        is_public=True,
        public_slug="public-test-slug",
    )

    response = client.get("/investigation/public-test-slug")

    assert response.status_code == 200
    assert 'name="robots" content="noindex,nofollow"' in response.text
    assert "Report this public result" in response.text
    assert "Make private" not in response.text
    assert "Was this investigation helpful?" not in response.text

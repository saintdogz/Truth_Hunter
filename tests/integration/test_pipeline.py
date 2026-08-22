"""End-to-end Phase 2 pipeline test with all external providers mocked."""

from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import Investigation
from app.investigation.fetcher import SafeSourceFetcher
from app.investigation.models import (
    AssessmentDraft,
    ClaimInterpretation,
    EvidenceAssessment,
    EvidencePosition,
    InvestigationSummary,
    SearchQueries,
    SearchResult,
    SourceDocument,
    SourceType,
    Verdict,
)
from app.investigation.pipeline import InvestigationPipeline
from app.investigation.repository import InvestigationRepository


class FakeAI:
    model_name = "fake-structured-model"

    def __init__(self) -> None:
        self.source_text_lengths: list[int] = []

    async def interpret_claim(self, claim: str, detected_language: str) -> ClaimInterpretation:
        return ClaimInterpretation(
            interpreted_claim=claim,
            language=detected_language,
            claim_type="factual",
            confidence=0.95,
        )

    async def generate_search_queries(self, claim: str, detected_language: str) -> SearchQueries:
        return SearchQueries(english=[claim], hungarian=[f"magyar {claim}"])

    async def evaluate_evidence(self, claim: str, source: SourceDocument) -> EvidenceAssessment:
        self.source_text_lengths.append(len(source.text))
        return EvidenceAssessment(
            position=EvidencePosition.SUPPORTING,
            strength=0.9,
            relevance=0.9,
            quality=0.9,
            independence=0.9,
            recency=0.9,
            source_type=SourceType.PRIMARY_RESEARCH,
            summary=f"Evidence from {source.domain}",
            excerpt="Relevant excerpt",
        )

    async def generate_summary(
        self,
        claim: str,
        assessment: AssessmentDraft,
        evidence: list[EvidenceAssessment],
        language: str,
    ) -> InvestigationSummary:
        assert assessment.verdict == Verdict.TRUE
        return InvestigationSummary(
            explanation="The application-calculated evidence strongly supports the claim.",
            pro_arguments=["Several independent sources support it."],
        )


class FakeSearch:
    provider_name = "fake-search"

    async def search(self, query: str, language: str, limit: int) -> list[SearchResult]:
        del query, limit
        return [
            SearchResult(url=f"https://{language}{number}.example/article?utm_source=test")
            for number in range(1, 6)
        ]


class FakeFetcher(SafeSourceFetcher):
    def __init__(self) -> None:
        pass

    async def fetch(self, result: SearchResult) -> SourceDocument:
        host = result.url.host or "unknown.example"
        return SourceDocument(
            url=result.url,
            title="Source",
            domain=host,
            text="A sufficiently detailed source document containing relevant evidence.",
        )


@pytest.mark.anyio
async def test_pipeline_persists_historical_snapshot() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    original = "The published report contains the stated result."
    confirmed = "The published report contains the stated result for 2025."

    with Session(engine) as session:
        ai = FakeAI()
        pipeline = InvestigationPipeline(
            ai,
            FakeSearch(),
            FakeFetcher(),
            InvestigationRepository(session),
            useful_source_limit=5,
            source_evaluation_limit=5,
            ai_source_text_max_chars=24,
        )
        investigation_id, interpretation = await pipeline.create_and_interpret(original)
        assert isinstance(investigation_id, UUID)
        assert interpretation.interpreted_claim == original

        assessment = await pipeline.investigate_confirmed(
            investigation_id, confirmed, corrected=True
        )
        stored = session.scalar(select(Investigation).where(Investigation.id == investigation_id))

        assert assessment.verdict == Verdict.TRUE
        assert stored is not None
        assert stored.original_claim == original
        assert stored.interpreted_claim == confirmed
        assert stored.correction_used is True
        assert stored.status == "COMPLETED"
        assert stored.source_count == 5
        assert stored.scoring_version == "evidence-v1"
        assert stored.prompt_version == "phase2-prompts-v1"
        assert len(stored.sources) == 5
        assert len(stored.evidence) == 5
        assert ai.source_text_lengths == [24] * 5
        with pytest.raises(ValueError, match="single claim correction"):
            InvestigationRepository(session).save_confirmed_claim(
                investigation_id, "A second correction", corrected=True
            )

    engine.dispose()

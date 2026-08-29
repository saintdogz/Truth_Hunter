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
from app.investigation.pipeline import InvestigationPipeline, InvestigationPipelineError
from app.investigation.repository import InvestigationRepository
from app.search.base import SearchAuthenticationError, SearchProviderError, SearchUnavailableError


class FakeAI:
    model_name = "fake-structured-model"

    def __init__(self, search_queries: SearchQueries | None = None) -> None:
        self.source_text_lengths: list[int] = []
        self.summary_calls = 0
        self.search_queries = search_queries

    async def interpret_claim(self, claim: str, detected_language: str) -> ClaimInterpretation:
        return ClaimInterpretation(
            interpreted_claim=claim,
            language=detected_language,
            claim_type="factual",
            confidence=0.95,
        )

    async def generate_search_queries(self, claim: str, detected_language: str) -> SearchQueries:
        return self.search_queries or SearchQueries(
            scope="general", use_hungarian=False, english=[claim], hungarian=[]
        )

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
        self.summary_calls += 1
        assert assessment.verdict == Verdict.TRUE
        return InvestigationSummary(
            explanation="The application-calculated evidence strongly supports the claim.",
            pro_arguments=["Several independent sources support it."],
        )


class FakeSearch:
    provider_name = "fake-search"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def search(self, query: str, language: str, limit: int) -> list[SearchResult]:
        del limit
        self.calls.append((query, language))
        return [
            SearchResult(url=f"https://{language}{number}.example/article?utm_source=test")
            for number in range(1, 6)
        ]


class EmptySearch:
    provider_name = "empty-search"

    async def search(self, query: str, language: str, limit: int) -> list[SearchResult]:
        del query, language, limit
        return []


class FailingSearch:
    provider_name = "failing-search"

    def __init__(self, error: SearchProviderError) -> None:
        self.error = error
        self.calls = 0

    async def search(self, query: str, language: str, limit: int) -> list[SearchResult]:
        del query, language, limit
        self.calls += 1
        raise self.error


class IrrelevantAI(FakeAI):
    async def evaluate_evidence(self, claim: str, source: SourceDocument) -> EvidenceAssessment:
        del claim, source
        return EvidenceAssessment(
            position=EvidencePosition.NEUTRAL,
            strength=0.0,
            relevance=0.1,
            quality=0.8,
            independence=0.5,
            recency=0.5,
            source_type=SourceType.UNKNOWN,
            summary="The page does not address the investigated claim.",
            excerpt="Unrelated material",
        )


class FallbackAwareAI(IrrelevantAI):
    async def evaluate_evidence(self, claim: str, source: SourceDocument) -> EvidenceAssessment:
        if source.domain.startswith("brave"):
            return await FakeAI.evaluate_evidence(self, claim, source)
        return await super().evaluate_evidence(claim, source)


class FlexibleSummaryAI(FallbackAwareAI):
    async def generate_summary(
        self,
        claim: str,
        assessment: AssessmentDraft,
        evidence: list[EvidenceAssessment],
        language: str,
    ) -> InvestigationSummary:
        del claim, assessment, evidence, language
        return InvestigationSummary(explanation="The available evidence was assessed.")


class FakeBraveSearch:
    provider_name = "brave"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def search(self, query: str, language: str, limit: int) -> list[SearchResult]:
        del limit
        self.calls.append((query, language))
        return [SearchResult(url=f"https://brave{len(self.calls)}.example/evidence")]


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
        assert stored.scoring_version == "evidence-v4"
        assert stored.prompt_version == "claim-interpretation-v2-adaptive-search-v6"
        assert stored.search_languages == ["en"]
        assert len(stored.sources) == 5
        assert len(stored.evidence) == 5
        assert ai.source_text_lengths == [24] * 5
        with pytest.raises(ValueError, match="single claim correction"):
            InvestigationRepository(session).save_confirmed_claim(
                investigation_id, "A second correction", corrected=True
            )

    engine.dispose()


@pytest.mark.anyio
async def test_hungary_specific_plan_adds_targeted_hungarian_search() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ai = FakeAI(
            SearchQueries(
                scope="hungary_specific",
                use_hungarian=True,
                english=["Hungary official statistics"],
                hungarian=["Magyarország hivatalos statisztika"],
            )
        )
        search = FakeSearch()
        pipeline = InvestigationPipeline(
            ai,
            search,
            FakeFetcher(),
            InvestigationRepository(session),
            useful_source_limit=2,
            source_evaluation_limit=2,
            search_delay_seconds=0,
        )
        investigation_id, _ = await pipeline.create_and_interpret(
            "A magyar hivatal közzétette az adatot."
        )

        await pipeline.investigate_confirmed(
            investigation_id, "A magyar hivatal közzétette az adatot."
        )

        stored = session.get(Investigation, investigation_id)
        assert search.calls == [
            ("Hungary official statistics", "en"),
            ("Magyarország hivatalos statisztika", "hu"),
        ]
        assert stored is not None
        assert stored.search_languages == ["en", "hu"]
    engine.dispose()


@pytest.mark.anyio
async def test_zero_search_results_fail_without_generating_summary() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ai = FakeAI()
        pipeline = InvestigationPipeline(
            ai,
            EmptySearch(),
            FakeFetcher(),
            InvestigationRepository(session),
            search_delay_seconds=0,
        )
        investigation_id, _ = await pipeline.create_and_interpret(
            "The Moon landing footage was filmed in a studio."
        )

        with pytest.raises(InvestigationPipelineError, match="Evidence search failed"):
            await pipeline.investigate_confirmed(
                investigation_id, "The Moon landing footage was filmed in a studio."
            )

        stored = session.get(Investigation, investigation_id)
        assert stored is not None
        assert stored.status == "SEARCH_FAILED"
        assert stored.summary is None
        assert stored.pro_arguments == []
        assert stored.contra_arguments == []
        assert stored.source_count == 0
        assert ai.summary_calls == 0
    engine.dispose()


@pytest.mark.anyio
async def test_irrelevant_fetched_pages_fail_without_generating_summary() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ai = IrrelevantAI()
        pipeline = InvestigationPipeline(
            ai,
            FakeSearch(),
            FakeFetcher(),
            InvestigationRepository(session),
            search_delay_seconds=0,
        )
        investigation_id, _ = await pipeline.create_and_interpret(
            "The Moon landing footage was filmed in a studio."
        )

        with pytest.raises(InvestigationPipelineError, match="Evidence search failed"):
            await pipeline.investigate_confirmed(
                investigation_id, "The Moon landing footage was filmed in a studio."
            )

        stored = session.get(Investigation, investigation_id)
        assert stored is not None
        assert stored.status == "SEARCH_FAILED"
        assert stored.summary is None
        assert stored.source_count == 0
        assert ai.summary_calls == 0
    engine.dispose()


@pytest.mark.anyio
async def test_brave_fallback_runs_only_after_free_evidence_is_not_useful() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ai = FallbackAwareAI(
            SearchQueries(
                scope="general",
                use_hungarian=False,
                english=["query one", "query two", "query three"],
                hungarian=[],
            )
        )
        fallback = FakeBraveSearch()
        pipeline = InvestigationPipeline(
            ai,
            FakeSearch(),
            FakeFetcher(),
            InvestigationRepository(session),
            search_delay_seconds=0,
            fallback_search=fallback,
            fallback_search_query_limit=2,
        )
        investigation_id, _ = await pipeline.create_and_interpret(
            "The Moon landing footage was filmed in a studio."
        )

        await pipeline.investigate_confirmed(
            investigation_id, "The Moon landing footage was filmed in a studio."
        )

        stored = session.get(Investigation, investigation_id)
        assert fallback.calls == [("query one", "en"), ("query two", "en")]
        assert stored is not None
        assert stored.status == "COMPLETED"
        assert stored.search_provider == "fake-search -> brave"
    engine.dispose()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "expected_primary_calls"),
    [
        (SearchAuthenticationError("Primary"), 1),
        (SearchUnavailableError("Primary"), 3),
    ],
)
async def test_search_retry_policy_distinguishes_permanent_and_transient_failures(
    error: SearchProviderError, expected_primary_calls: int
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        primary = FailingSearch(error)
        fallback = FakeBraveSearch()
        pipeline = InvestigationPipeline(
            FlexibleSummaryAI(),
            primary,
            FakeFetcher(),
            InvestigationRepository(session),
            search_delay_seconds=0,
            search_retry_attempts=2,
            fallback_search=fallback,
        )
        investigation_id, _ = await pipeline.create_and_interpret("A testable factual claim.")

        assessment = await pipeline.investigate_confirmed(
            investigation_id, "A testable factual claim."
        )

        assert primary.calls == expected_primary_calls
        assert fallback.calls == [("A testable factual claim.", "en")]
        assert assessment.verdict == Verdict.INCONCLUSIVE
    engine.dispose()

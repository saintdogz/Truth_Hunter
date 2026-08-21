"""Phase 2 investigation orchestration without UI or background infrastructure."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from app.ai.base import AIProvider
from app.investigation.claim import detect_language, validate_claim, validate_interpretation
from app.investigation.fetcher import SafeSourceFetcher, SourceFetchError, UnsafeUrlError
from app.investigation.models import (
    AssessmentDraft,
    ClaimInterpretation,
    ClaimType,
    EvidenceAssessment,
    SearchResult,
)
from app.investigation.prompts import PROMPT_VERSION
from app.investigation.repository import InvestigationRepository
from app.investigation.scoring import calculate_balance
from app.investigation.verdict import calculate_assessment
from app.search.base import SearchProvider

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_NAMES = {"fbclid", "gclid", "mc_cid", "mc_eid"}


class InvestigationPipelineError(RuntimeError):
    """Sanitized terminal pipeline failure."""


def canonical_url(url: str) -> str:
    """Normalize common duplicate URL variants while preserving meaningful parameters."""

    parsed = urlsplit(url)
    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_NAMES
        and not key.lower().startswith(TRACKING_QUERY_PREFIXES)
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            urlencode(filtered_query),
            "",
        )
    )


def deduplicate_results(results: list[SearchResult]) -> list[SearchResult]:
    unique: dict[str, SearchResult] = {}
    for result in results:
        unique.setdefault(canonical_url(str(result.url)), result)
    return list(unique.values())


class InvestigationPipeline:
    def __init__(
        self,
        ai: AIProvider,
        search: SearchProvider,
        fetcher: SafeSourceFetcher,
        repository: InvestigationRepository,
        *,
        search_result_limit: int = 20,
        useful_source_limit: int = 15,
    ) -> None:
        self._ai = ai
        self._search = search
        self._fetcher = fetcher
        self._repository = repository
        self._search_result_limit = search_result_limit
        self._useful_source_limit = useful_source_limit

    async def create_and_interpret(self, original_claim: str) -> tuple[UUID, ClaimInterpretation]:
        validate_claim(original_claim)
        investigation = self._repository.create(original_claim)
        self._repository.set_status(investigation.id, "INTERPRETING")
        try:
            language = detect_language(original_claim)
            interpretation = await self._ai.interpret_claim(original_claim, language)
            validate_interpretation(original_claim, interpretation)
            self._repository.save_interpretation(investigation.id, interpretation)
        except Exception as exc:
            self._repository.set_status(investigation.id, "FAILED")
            raise InvestigationPipelineError("Claim interpretation failed") from exc
        return investigation.id, interpretation

    async def investigate_confirmed(
        self, investigation_id: UUID, confirmed_claim: str, *, corrected: bool = False
    ) -> AssessmentDraft:
        validate_claim(confirmed_claim)
        investigation = self._repository.get(investigation_id)
        language = investigation.language or detect_language(confirmed_claim)
        claim_type_value = investigation.claim_type or "factual"
        self._repository.save_confirmed_claim(
            investigation_id, confirmed_claim, corrected=corrected
        )

        try:
            self._repository.set_status(investigation_id, "SEARCHING")
            queries = await self._ai.generate_search_queries(confirmed_claim, language)
            candidates: list[SearchResult] = []
            for query_language, query_list in (("en", queries.english), ("hu", queries.hungarian)):
                for query in query_list:
                    candidates.extend(
                        await self._search.search(query, query_language, self._search_result_limit)
                    )
            candidates = deduplicate_results(candidates)

            self._repository.set_status(investigation_id, "COLLECTING_SOURCES")
            evidence: list[EvidenceAssessment] = []
            evaluated_count = 0
            for candidate in candidates:
                if len(evidence) >= self._useful_source_limit:
                    break
                try:
                    document = await self._fetcher.fetch(candidate)
                except (SourceFetchError, UnsafeUrlError):
                    continue
                source = self._repository.add_source(investigation_id, document)
                self._repository.set_status(investigation_id, "EVALUATING_EVIDENCE")
                item = await self._ai.evaluate_evidence(confirmed_claim, document)
                evaluated_count += 1
                item = item.model_copy(update={"source_id": source.id})
                self._repository.add_evidence(investigation_id, source, item)
                if item.relevance >= 0.35:
                    evidence.append(item)

            self._repository.set_status(investigation_id, "CALCULATING_ASSESSMENT")
            balance = calculate_balance(evidence)
            assessment = calculate_assessment(evidence, balance, ClaimType(claim_type_value))

            self._repository.set_status(investigation_id, "GENERATING_RESULT")
            summary = await self._ai.generate_summary(
                confirmed_claim, assessment, evidence, language
            )
            self._repository.complete(
                investigation_id,
                assessment,
                summary,
                ai_model=self._ai.model_name,
                prompt_version=PROMPT_VERSION,
                search_provider=self._search.provider_name,
                source_count=evaluated_count,
            )
            return assessment
        except Exception as exc:
            self._repository.set_status(investigation_id, "FAILED")
            raise InvestigationPipelineError("Investigation failed") from exc

    async def aclose(self) -> None:
        """Close provider-owned network clients when the pipeline scope ends."""

        for component in (self._ai, self._search, self._fetcher):
            close = getattr(component, "close", None)
            if close is not None:
                await close()

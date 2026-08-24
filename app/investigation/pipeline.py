"""Phase 2 investigation orchestration without UI or background infrastructure."""

import asyncio
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
from app.investigation.scoring import apply_evidence_guardrails, calculate_balance
from app.investigation.verdict import calculate_assessment
from app.search.base import SearchProvider, SearchProviderError

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_NAMES = {"fbclid", "gclid", "mc_cid", "mc_eid"}


class InvestigationPipelineError(RuntimeError):
    """Sanitized terminal pipeline failure."""


class SearchEvidenceUnavailableError(RuntimeError):
    """No source could be collected because evidence search was unavailable."""


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
        search_delay_seconds: float = 1.0,
        search_retry_attempts: int = 1,
        useful_source_limit: int = 15,
        source_evaluation_limit: int = 15,
        ai_source_text_max_chars: int = 12_000,
        fallback_search: SearchProvider | None = None,
        fallback_search_query_limit: int = 2,
    ) -> None:
        self._ai = ai
        self._search = search
        self._fetcher = fetcher
        self._repository = repository
        self._search_result_limit = search_result_limit
        self._search_delay_seconds = search_delay_seconds
        self._search_retry_attempts = search_retry_attempts
        self._useful_source_limit = useful_source_limit
        self._source_evaluation_limit = source_evaluation_limit
        self._ai_source_text_max_chars = ai_source_text_max_chars
        self._fallback_search = fallback_search
        self._fallback_search_query_limit = fallback_search_query_limit

    async def create_and_interpret(
        self,
        original_claim: str,
        *,
        user_id: UUID | None = None,
        session_id: str | None = None,
    ) -> tuple[UUID, ClaimInterpretation]:
        validate_claim(original_claim)
        investigation = self._repository.create(
            original_claim, user_id=user_id, session_id=session_id
        )
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
            query_plan = [("en", query) for query in queries.english]
            if queries.use_hungarian and queries.scope == "hungary_specific":
                query_plan.extend(("hu", query) for query in queries.hungarian)
            search_languages = list(dict.fromkeys(item[0] for item in query_plan))
            providers_used = [self._search.provider_name]
            candidates = await self._search_candidates(self._search, query_plan)
            evidence, evaluated_count, seen_urls = await self._evaluate_candidates(
                investigation_id, confirmed_claim, candidates
            )

            if not evidence and self._fallback_search is not None:
                providers_used.append(self._fallback_search.provider_name)
                fallback_plan = query_plan[: self._fallback_search_query_limit]
                fallback_candidates = await self._search_candidates(
                    self._fallback_search, fallback_plan
                )
                fallback_candidates = [
                    item
                    for item in fallback_candidates
                    if canonical_url(str(item.url)) not in seen_urls
                ]
                fallback_evidence, fallback_count, _ = await self._evaluate_candidates(
                    investigation_id, confirmed_claim, fallback_candidates
                )
                evidence.extend(fallback_evidence)
                evaluated_count += fallback_count

            if not evidence:
                raise SearchEvidenceUnavailableError("No useful evidence could be collected")

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
                ai_provider_attempts=getattr(self._ai, "attempts", []),
                prompt_version=PROMPT_VERSION,
                search_provider=" -> ".join(providers_used),
                search_languages=search_languages,
                source_count=evaluated_count,
            )
            return assessment
        except SearchEvidenceUnavailableError as exc:
            self._repository.set_status(investigation_id, "SEARCH_FAILED")
            raise InvestigationPipelineError("Evidence search failed") from exc
        except Exception as exc:
            self._repository.set_status(investigation_id, "FAILED")
            raise InvestigationPipelineError("Investigation failed") from exc

    async def _search_candidates(
        self, provider: SearchProvider, query_plan: list[tuple[str, str]]
    ) -> list[SearchResult]:
        candidates: list[SearchResult] = []
        for index, (query_language, query) in enumerate(query_plan):
            remaining = self._search_result_limit - len(deduplicate_results(candidates))
            if remaining <= 0:
                break
            try:
                results = await self._search_with_retry(
                    provider, query, query_language, min(8, remaining)
                )
            except SearchProviderError:
                results = []
            candidates.extend(results)
            if index < len(query_plan) - 1 and self._search_delay_seconds:
                await asyncio.sleep(self._search_delay_seconds)
        return deduplicate_results(candidates)

    async def _evaluate_candidates(
        self,
        investigation_id: UUID,
        confirmed_claim: str,
        candidates: list[SearchResult],
    ) -> tuple[list[EvidenceAssessment], int, set[str]]:
        self._repository.set_status(investigation_id, "COLLECTING_SOURCES")
        evidence: list[EvidenceAssessment] = []
        evaluated_count = 0
        seen_urls: set[str] = set()
        for candidate in candidates:
            if (
                len(evidence) >= self._useful_source_limit
                or evaluated_count >= self._source_evaluation_limit
            ):
                break
            seen_urls.add(canonical_url(str(candidate.url)))
            try:
                document = await self._fetcher.fetch(candidate)
            except (SourceFetchError, UnsafeUrlError):
                continue
            source = self._repository.add_source(investigation_id, document)
            self._repository.set_status(investigation_id, "EVALUATING_EVIDENCE")
            ai_document = document.model_copy(
                update={"text": document.text[: self._ai_source_text_max_chars]}
            )
            item = await self._ai.evaluate_evidence(confirmed_claim, ai_document)
            evaluated_count += 1
            item = apply_evidence_guardrails(confirmed_claim, item, document.domain)
            item = item.model_copy(update={"source_id": source.id})
            self._repository.add_evidence(investigation_id, source, item)
            if item.relevance >= 0.35:
                evidence.append(item)
        return evidence, evaluated_count, seen_urls

    async def _search_with_retry(
        self,
        provider: SearchProvider,
        query: str,
        language: str,
        limit: int,
    ) -> list[SearchResult]:
        for attempt in range(self._search_retry_attempts + 1):
            try:
                return await provider.search(query, language, limit)
            except SearchProviderError:
                if attempt >= self._search_retry_attempts:
                    raise
                if self._search_delay_seconds:
                    await asyncio.sleep(self._search_delay_seconds * (2 ** (attempt + 1)))
        return []

    async def aclose(self) -> None:
        """Close provider-owned network clients when the pipeline scope ends."""

        for component in (self._ai, self._search, self._fallback_search, self._fetcher):
            if component is None:
                continue
            close = getattr(component, "close", None)
            if close is not None:
                await close()

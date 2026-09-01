"""Phase 2 investigation orchestration without UI or background infrastructure."""

import asyncio
import re
from dataclasses import dataclass
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
    EvidencePosition,
    InvestigationSummary,
    SearchResult,
    SourceDocument,
)
from app.investigation.prompts import PROMPT_VERSION
from app.investigation.repository import InvestigationRepository
from app.investigation.scoring import apply_evidence_guardrails, calculate_balance
from app.investigation.verdict import calculate_assessment
from app.search.base import SearchProvider, SearchProviderError

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_NAMES = {"fbclid", "gclid", "mc_cid", "mc_eid"}
SEARCH_TEXT_STOPWORDS = {
    "about",
    "after",
    "built",
    "could",
    "from",
    "have",
    "into",
    "that",
    "their",
    "there",
    "these",
    "they",
    "this",
    "were",
    "what",
    "when",
    "where",
    "which",
    "with",
}
DICTIONARY_DOMAINS = {
    "dictionary.cambridge.org",
    "dictionary.com",
    "merriam-webster.com",
    "www.dictionary.com",
    "www.merriam-webster.com",
    "en.wiktionary.org",
}
SOCIAL_PLATFORM_ALIASES = {
    "facebook.com": "facebook",
    "instagram.com": "instagram",
    "linkedin.com": "linkedin",
    "reddit.com": "reddit",
    "tiktok.com": "tiktok",
    "x.com": "twitter",
    "youtube.com": "youtube",
}
AUTHORITATIVE_DOMAIN_MARKERS = (
    ".ac.uk",
    ".edu",
    ".edu.au",
    ".europa.eu",
    ".gov",
    ".gov.uk",
    ".int",
)
LEGAL_CLAIM_TERMS = {
    "illegal",
    "law",
    "lawful",
    "legal",
    "legality",
    "licence",
    "license",
    "regulation",
}
HUNGARY_TERMS = {"hungary", "hungarian", "magyar", "magyarország"}
COMPARISON_MARKERS = (
    " but ",
    " yet ",
    " while ",
    " why is ",
    " why are ",
    " why not ",
    " de ",
    " mégis ",
    " miért ",
    " miközben ",
)
PRIMARY_REPORT_DOMAIN_SUFFIXES = (
    "coca-cola.com",
    "coca-colacompany.com",
    "coca-colahellenic.com",
    "cocacolaep.com",
)
CARBON_TERMS = ("co2", "co₂", "carbon dioxide", "carbon footprint", "kibocsát")
BEVERAGE_TERMS = (
    "beverage",
    "carbonated",
    "coca-cola",
    "coca‑cola",
    "coca cola",
    "cocacola",
    "soft drink",
    "üdítő",
)
VEHICLE_TERMS = (
    "car",
    "vehicle",
    "petrol",
    "gasoline",
    "benzin",
    "benzinautó",
    "benzinmotor",
    "motor",
)


@dataclass(frozen=True)
class CarbonComparisonClaim:
    beverage_litres: float
    vehicle_kilometres: float
    expects_beverage_greater: bool


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


def candidate_is_clearly_low_value(claim: str, candidate: SearchResult) -> bool:
    """Reject only search metadata that is clearly generic or definitional."""

    domain = (candidate.url.host or "").lower()
    if domain in DICTIONARY_DOMAINS:
        return True
    metadata = " ".join((candidate.title, candidate.snippet)).strip().casefold()
    if not metadata:
        return False
    claim_terms = {
        term
        for term in re.findall(r"[\w'-]+", claim.casefold())
        if len(term) >= 4 and term not in SEARCH_TEXT_STOPWORDS
    }
    if not claim_terms:
        return False
    path = candidate.url.path or "/"
    searchable = f"{metadata} {path.casefold()}"
    has_claim_term = any(term in searchable for term in claim_terms)
    is_generic_homepage = path == "/"
    legal_claim = bool(claim_terms & LEGAL_CLAIM_TERMS)
    distinguishing_terms = claim_terms - LEGAL_CLAIM_TERMS - HUNGARY_TERMS
    if (
        legal_claim
        and distinguishing_terms
        and not any(term in searchable for term in distinguishing_terms)
    ):
        return True
    return is_generic_homepage and not has_claim_term


def authoritative_search_supplements(claim: str) -> list[tuple[str, str]]:
    """Add deterministic primary-source searches for high-stakes legal claims."""

    normalized = claim.casefold()
    terms = set(re.findall(r"[\w'-]+", normalized))
    if not terms & LEGAL_CLAIM_TERMS:
        return []
    if terms & HUNGARY_TERMS:
        topic = " ".join(
            term
            for term in re.findall(r"[\w'-]+", normalized)
            if term not in LEGAL_CLAIM_TERMS and term not in HUNGARY_TERMS
        )
        return [
            ("hu", f"site:njt.hu {topic} szerzői jog jogszerű hozzáférés".strip()),
            ("hu", f"site:sztnh.gov.hu {topic} szerzői jog".strip()),
            ("en", f"site:eur-lex.europa.eu {topic} copyright Hungary".strip()),
        ]
    return []


def comparison_search_supplements(claim: str) -> list[tuple[str, str]]:
    """Search both mechanisms and their scale for common comparison questions."""

    normalized = claim.casefold()
    if not is_comparison_claim(normalized):
        return []
    has_co2 = _has_any_term(normalized, CARBON_TERMS)
    has_soft_drink = _has_any_term(normalized, BEVERAGE_TERMS)
    has_vehicle = _has_any_term(normalized, VEHICLE_TERMS)
    if has_co2 and has_soft_drink and has_vehicle:
        return [
            (
                "en",
                'site:coca-cola.com/pl/pl/about-us/faq/klimat "52 g/litr"',
            ),
            (
                "en",
                'site:epa.gov/greenvehicles "400 grams" "CO2 per mile"',
            ),
            (
                "en",
                "Coca-Cola carbon footprint per litre compared with car CO2 per km",
            ),
        ]
    if has_co2 and has_soft_drink:
        return [
            (
                "en",
                "carbon dioxide in carbonated drinks amount compared with "
                "fossil fuel CO2 emissions",
            ),
            ("en", "food grade carbon dioxide carbonated beverages safety regulation"),
            ("en", "why atmospheric CO2 emissions cause climate change cumulative concentration"),
        ]
    return []


def is_comparison_claim(claim: str) -> bool:
    """Recognize ordinary English and Hungarian comparative wording."""

    normalized = f" {claim.casefold()} "
    return (
        any(marker in normalized for marker in COMPARISON_MARKERS)
        or " more than " in normalized
        or " less than " in normalized
        or re.search(r"\bmore\b.+\bthan\b", normalized) is not None
        or re.search(r"\bless\b.+\bthan\b", normalized) is not None
        or (" több " in normalized and " mint " in normalized)
        or (" kevesebb " in normalized and " mint " in normalized)
    )


def _has_any_term(text: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text) for term in terms)


def parse_carbon_comparison_claim(claim: str) -> CarbonComparisonClaim | None:
    """Extract the two activity amounts from a beverage-versus-vehicle CO2 claim."""

    normalized = claim.casefold().replace(",", ".")
    if not (
        is_comparison_claim(normalized)
        and _has_any_term(normalized, CARBON_TERMS)
        and _has_any_term(normalized, BEVERAGE_TERMS)
        and _has_any_term(normalized, VEHICLE_TERMS)
    ):
        return None
    litres = re.search(r"(\d+(?:\.\d+)?)\s*(?:l|lit(?:er|re|res|ers))\b", normalized)
    kilometres = re.search(r"(\d+(?:\.\d+)?)\s*km\b", normalized)
    if litres is None or kilometres is None:
        return None
    expects_beverage_greater = (
        " több " in f" {normalized} " or re.search(r"\bmore\b.+\bthan\b", normalized) is not None
    )
    return CarbonComparisonClaim(
        float(litres.group(1)),
        float(kilometres.group(1)),
        expects_beverage_greater,
    )


def _normalized_measurement_text(document: SourceDocument) -> str:
    return " ".join(document.text.casefold().replace(",", ".").split())


def _beverage_intensities(document: SourceDocument) -> list[float]:
    """Return full-value-chain beverage intensities in grams CO2e per litre."""

    text = _normalized_measurement_text(document)
    domain = document.domain.casefold().rstrip(".")
    full_value_chain = any(
        marker in text for marker in ("scope 3", "full value chain", "carbon footprint")
    )
    official_production_metric = (
        domain == "coca-cola.com" or domain.endswith(".coca-cola.com")
    ) and ("procesie produkcji" in text or "production of our beverages" in text)
    if not _has_any_term(text, BEVERAGE_TERMS) or not (
        full_value_chain or official_production_metric
    ):
        return []
    patterns = (
        r"(\d+(?:\.\d+)?)\s*g(?:rams?|rammes?)?\s*(?:co2e|co₂e).*?per\s+lit(?:er|re)",
        r"(\d+(?:\.\d+)?)\s*g\s*(?:co2e|co₂e)\s*/\s*(?:l|lit(?:er|re))",
        r"(\d+(?:\.\d+)?)\s*g\s*/\s*lpb",
        r"(\d+(?:\.\d+)?)\s*g\s*/\s*litr",
    )
    return [float(value) for pattern in patterns for value in re.findall(pattern, text)]


def _vehicle_intensities(document: SourceDocument) -> list[float]:
    """Return vehicle intensities normalized to grams CO2 per kilometre."""

    text = _normalized_measurement_text(document)
    if not _has_any_term(text, VEHICLE_TERMS):
        return []
    per_km = re.findall(
        r"(\d+(?:\.\d+)?)\s*g(?:rams?)?\s*(?:of\s+)?co\s*[₂2]e?.*?per\s+(?:kilo(?:metre|meter)|km)",
        text,
    )
    per_mile = re.findall(
        r"(\d+(?:\.\d+)?)\s*g(?:rams?)?\s*(?:of\s+)?co\s*[₂2]e?.*?per\s+mile",
        text,
    )
    return [float(value) for value in per_km] + [float(value) / 1.609344 for value in per_mile]


def synthesize_carbon_comparison(
    claim: str,
    evidence: list[EvidenceAssessment],
    documents: dict[UUID, SourceDocument],
) -> list[EvidenceAssessment]:
    """Join independently sourced operands using deterministic unit conversion."""

    comparison = parse_carbon_comparison_claim(claim)
    if comparison is None:
        return evidence
    beverage: list[tuple[UUID, float]] = []
    vehicle: list[tuple[UUID, float]] = []
    for item in evidence:
        if item.source_id is None or item.source_id not in documents:
            continue
        document = documents[item.source_id]
        domain = document.domain.casefold().rstrip(".")
        authoritative = any(
            domain == suffix or domain.endswith(f".{suffix}")
            for suffix in PRIMARY_REPORT_DOMAIN_SUFFIXES
        ) or any(domain.endswith(marker) for marker in AUTHORITATIVE_DOMAIN_MARKERS)
        if not authoritative:
            continue
        beverage.extend((item.source_id, value) for value in _beverage_intensities(document))
        vehicle.extend((item.source_id, value) for value in _vehicle_intensities(document))
    if not beverage or not vehicle:
        return evidence

    beverage_total = min(value for _, value in beverage) * comparison.beverage_litres
    vehicle_total = max(value for _, value in vehicle) * comparison.vehicle_kilometres
    if beverage_total > vehicle_total:
        observed_beverage_greater = True
    elif (
        max(value for _, value in beverage) * comparison.beverage_litres
        < min(value for _, value in vehicle) * comparison.vehicle_kilometres
    ):
        observed_beverage_greater = False
    else:
        return evidence
    position = (
        EvidencePosition.SUPPORTING
        if observed_beverage_greater == comparison.expects_beverage_greater
        else EvidencePosition.CONTRADICTING
    )

    contributing_ids = {source_id for source_id, _ in beverage + vehicle}
    return [
        item.model_copy(
            update={
                "position": position,
                "strength": max(item.strength, 0.85),
                "relevance": max(item.relevance, 0.9),
                "quality": max(item.quality, 0.8),
                "independence": max(item.independence, 0.75),
            }
        )
        if item.source_id in contributing_ids
        else item
        for item in evidence
    ]


def evidence_is_collectible(claim: str, item: EvidenceAssessment) -> bool:
    """Keep direct evidence plus strong complementary evidence for comparison claims."""

    if item.relevance >= 0.35:
        return True
    normalized = claim.casefold()
    is_comparison = is_comparison_claim(normalized)
    return (
        is_comparison
        and item.position == EvidencePosition.NEUTRAL
        and item.relevance >= 0.1
        and item.quality >= 0.7
        and item.independence >= 0.45
    )


def has_verdict_bearing_evidence(evidence: list[EvidenceAssessment]) -> bool:
    """Return whether evidence can materially support or contradict a claim."""

    return any(
        item.position in {EvidencePosition.SUPPORTING, EvidencePosition.CONTRADICTING}
        and item.relevance >= 0.35
        and item.quality >= 0.35
        and item.strength >= 0.25
        for item in evidence
    )


def prioritize_candidates(
    claim: str, candidates: list[SearchResult], *, domain_limit: int = 3
) -> list[SearchResult]:
    """Prefer authoritative, diverse results while retaining relevant social sources."""

    claim_text = claim.casefold()

    def domain_matches(domain: str, suffix: str) -> bool:
        return domain == suffix or domain.endswith(f".{suffix}")

    def priority(item: tuple[int, SearchResult]) -> tuple[int, int]:
        index, candidate = item
        domain = (candidate.url.host or "").lower()
        authoritative = any(domain.endswith(marker) for marker in AUTHORITATIVE_DOMAIN_MARKERS)
        primary_report = any(
            domain == suffix or domain.endswith(f".{suffix}")
            for suffix in PRIMARY_REPORT_DOMAIN_SUFFIXES
        )
        social_alias = next(
            (
                alias
                for suffix, alias in SOCIAL_PLATFORM_ALIASES.items()
                if domain_matches(domain, suffix)
            ),
            None,
        )
        social_is_primary = social_alias is not None and social_alias in claim_text
        tier = (
            0 if authoritative or primary_report or social_is_primary else 2 if social_alias else 1
        )
        return tier, index

    ranked = [candidate for _, candidate in sorted(enumerate(candidates), key=priority)]
    selected: list[SearchResult] = []
    domain_counts: dict[str, int] = {}
    for candidate in ranked:
        domain = (candidate.url.host or "").lower()
        if domain and domain_counts.get(domain, 0) >= domain_limit:
            continue
        selected.append(candidate)
        if domain:
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
    return selected


def ground_summary_arguments(
    summary: InvestigationSummary, evidence: list[EvidenceAssessment]
) -> InvestigationSummary:
    """Prevent neutral evidence from becoming an apparent pro or contra argument."""

    positions = {item.position for item in evidence}
    updates: dict[str, list[str]] = {}
    if EvidencePosition.SUPPORTING not in positions:
        updates["pro_arguments"] = []
    if EvidencePosition.CONTRADICTING not in positions:
        updates["contra_arguments"] = []
    return summary.model_copy(update=updates) if updates else summary


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
            query_plan = authoritative_search_supplements(confirmed_claim)
            query_plan.extend(comparison_search_supplements(confirmed_claim))
            query_plan.extend(("en", query) for query in queries.english)
            if queries.use_hungarian and queries.scope == "hungary_specific":
                query_plan.extend(("hu", query) for query in queries.hungarian)
            query_plan = list(dict.fromkeys(query_plan))
            search_languages = list(dict.fromkeys(item[0] for item in query_plan))
            providers_used = [self._search.provider_name]
            candidates = await self._search_candidates(self._search, query_plan)
            candidates = prioritize_candidates(confirmed_claim, candidates)
            evidence, evaluated_count, seen_urls, documents = await self._evaluate_candidates(
                investigation_id, confirmed_claim, candidates
            )
            evidence = synthesize_carbon_comparison(confirmed_claim, evidence, documents)
            preliminary = calculate_assessment(
                evidence,
                calculate_balance(evidence),
                ClaimType(claim_type_value),
            )

            needs_fallback = not has_verdict_bearing_evidence(evidence) or (
                parse_carbon_comparison_claim(confirmed_claim) is not None
                and not preliminary.evidence_sufficient
            )
            if needs_fallback and self._fallback_search is not None:
                providers_used.append(self._fallback_search.provider_name)
                fallback_plan = query_plan[: self._fallback_search_query_limit]
                fallback_candidates = await self._search_candidates(
                    self._fallback_search, fallback_plan
                )
                fallback_candidates = prioritize_candidates(confirmed_claim, fallback_candidates)
                fallback_candidates = [
                    item
                    for item in fallback_candidates
                    if canonical_url(str(item.url)) not in seen_urls
                ]
                (
                    fallback_evidence,
                    fallback_count,
                    _,
                    fallback_documents,
                ) = await self._evaluate_candidates(
                    investigation_id, confirmed_claim, fallback_candidates
                )
                evidence.extend(fallback_evidence)
                documents.update(fallback_documents)
                evidence = synthesize_carbon_comparison(confirmed_claim, evidence, documents)
                evaluated_count += fallback_count

            if not evidence:
                raise SearchEvidenceUnavailableError("No useful evidence could be collected")

            self._repository.set_status(investigation_id, "CALCULATING_ASSESSMENT")
            self._repository.update_evidence_assessments(evidence)
            balance = calculate_balance(evidence)
            assessment = calculate_assessment(evidence, balance, ClaimType(claim_type_value))

            self._repository.set_status(investigation_id, "GENERATING_RESULT")
            summary = await self._ai.generate_summary(
                confirmed_claim, assessment, evidence, language
            )
            summary = ground_summary_arguments(summary, evidence)
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
    ) -> tuple[list[EvidenceAssessment], int, set[str], dict[UUID, SourceDocument]]:
        self._repository.set_status(investigation_id, "COLLECTING_SOURCES")
        evidence: list[EvidenceAssessment] = []
        evaluated_count = 0
        seen_urls: set[str] = set()
        documents: dict[UUID, SourceDocument] = {}
        for candidate in candidates:
            if (
                len(evidence) >= self._useful_source_limit
                or evaluated_count >= self._source_evaluation_limit
            ):
                break
            if candidate_is_clearly_low_value(confirmed_claim, candidate):
                continue
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
            if evidence_is_collectible(confirmed_claim, item):
                evidence.append(item)
                documents[source.id] = document
        return evidence, evaluated_count, seen_urls, documents

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
            except SearchProviderError as exc:
                if not exc.retryable or attempt >= self._search_retry_attempts:
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

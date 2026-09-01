"""Conservative search-candidate and result-summary quality gates."""

from uuid import uuid4

from app.investigation.models import (
    EvidenceAssessment,
    EvidencePosition,
    InvestigationSummary,
    SearchResult,
    SourceDocument,
    SourceType,
)
from app.investigation.pipeline import (
    authoritative_search_supplements,
    candidate_is_clearly_low_value,
    comparison_search_supplements,
    evidence_is_collectible,
    ground_summary_arguments,
    has_verdict_bearing_evidence,
    prioritize_candidates,
    synthesize_carbon_comparison,
)


def evidence(position: EvidencePosition) -> EvidenceAssessment:
    return EvidenceAssessment(
        position=position,
        strength=0.8,
        relevance=0.8,
        quality=0.8,
        independence=0.8,
        recency=0.8,
        source_type=SourceType.ACADEMIC,
        summary="Grounded evidence",
    )


def test_dictionary_and_unrelated_generic_results_are_rejected() -> None:
    claim = "The pyramids were constructed to harness energy."

    assert candidate_is_clearly_low_value(
        claim,
        SearchResult(
            url="https://dictionary.cambridge.org/dictionary/english/archaeological",
            title="ARCHAEOLOGICAL | English meaning",
            snippet="A definition of the word archaeological.",
        ),
    )
    assert candidate_is_clearly_low_value(
        claim,
        SearchResult(
            url="https://www.scientificamerican.com/",
            title="Scientific American",
            snippet="Science news covering health, space, climate and technology.",
        ),
    )


def test_relevant_or_metadata_free_results_are_kept_conservatively() -> None:
    claim = "The pyramids were constructed to harness energy."

    assert not candidate_is_clearly_low_value(
        claim,
        SearchResult(
            url="https://giza.fas.harvard.edu/faq/",
            title="Digital Giza frequently asked questions",
            snippet="The pyramids were burial places for Egyptian royalty.",
        ),
    )
    assert not candidate_is_clearly_low_value(
        claim, SearchResult(url="https://museum.example/research/pyramids")
    )


def test_hungarian_legal_claim_gets_primary_source_queries() -> None:
    queries = authoritative_search_supplements(
        "Downloading torrents is legal in Hungary, but seeding is illegal."
    )

    assert queries[0][0] == "hu"
    assert "site:njt.hu" in queries[0][1]
    assert any("site:sztnh.gov.hu" in query for _, query in queries)
    assert any("site:eur-lex.europa.eu" in query for _, query in queries)


def test_generic_country_pages_are_rejected_for_legal_claims() -> None:
    claim = "Downloading torrents is legal in Hungary, but seeding is illegal."

    assert candidate_is_clearly_low_value(
        claim,
        SearchResult(
            url="https://en.wikipedia.org/wiki/Hungary",
            title="Hungary",
            snippet="Hungary is a landlocked country in Central Europe.",
        ),
    )


def test_neutral_forum_comment_does_not_block_search_fallback() -> None:
    assert not has_verdict_bearing_evidence([evidence(EvidencePosition.NEUTRAL)])
    assert has_verdict_bearing_evidence([evidence(EvidencePosition.CONTRADICTING)])


def test_co2_comparison_gets_scale_and_mechanism_queries() -> None:
    queries = comparison_search_supplements(
        "CO2 causes significant harm, but carbonated soft drinks are not prohibited."
    )

    assert len(queries) == 3
    assert any("amount compared" in query for _, query in queries)
    assert any("food grade" in query for _, query in queries)
    assert any("atmospheric CO2" in query for _, query in queries)


def test_hungarian_quantitative_carbon_comparison_gets_operand_queries() -> None:
    queries = comparison_search_supplements(
        "10l Coca-Cola több CO2-t bocsát ki mint egy benzinautó 1km alatt."
    )

    assert any("coca-cola.com" in query for _, query in queries)
    assert any("epa.gov" in query for _, query in queries)


def test_independent_official_operands_are_joined_with_deterministic_units() -> None:
    beverage_id = uuid4()
    vehicle_id = uuid4()
    items = [
        evidence(EvidencePosition.NEUTRAL).model_copy(update={"source_id": beverage_id}),
        evidence(EvidencePosition.NEUTRAL).model_copy(update={"source_id": vehicle_id}),
    ]
    documents = {
        beverage_id: SourceDocument(
            url="https://www.coca-cola.com/pl/pl/about-us/faq/klimat",
            domain="www.coca-cola.com",
            text=(
                "Coca‑Cola zmniejsza ilość CO2 emitowanego w procesie produkcji naszych "
                "napojów. Obecnie wynosi 52 g/litr produktu."
            ),
        ),
        vehicle_id: SourceDocument(
            url="https://www.epa.gov/greenvehicles/passenger-vehicle",
            domain="www.epa.gov",
            text="The average gasoline passenger vehicle emits 400 grams of CO 2 per mile.",
        ),
    }

    synthesized = synthesize_carbon_comparison(
        "10l Coca-Cola emits more CO2 than a petrol car driving 1km.", items, documents
    )

    assert [item.position for item in synthesized] == [
        EvidencePosition.SUPPORTING,
        EvidencePosition.SUPPORTING,
    ]
    assert all(item.relevance >= 0.9 for item in synthesized)

    reversed_claim = synthesize_carbon_comparison(
        "10l Coca-Cola emits less CO2 than a petrol car driving 1km.", items, documents
    )
    assert all(item.position == EvidencePosition.CONTRADICTING for item in reversed_claim)


def test_comparison_claim_retains_high_quality_complementary_evidence() -> None:
    partial = evidence(EvidencePosition.NEUTRAL).model_copy(
        update={"relevance": 0.15, "quality": 0.9, "independence": 0.8}
    )

    assert evidence_is_collectible("CO2 is harmful, yet carbonated drinks are permitted.", partial)
    assert not evidence_is_collectible("CO2 is harmful.", partial)


def test_candidates_prefer_authoritative_sources_and_limit_repeated_domains() -> None:
    candidates = [
        SearchResult(url="https://facebook.com/posts/1", title="Post one"),
        SearchResult(url="https://example.com/a", title="Article A"),
        SearchResult(url="https://example.com/b", title="Article B"),
        SearchResult(url="https://example.com/c", title="Article C"),
        SearchResult(url="https://example.com/d", title="Article D"),
        SearchResult(url="https://science.nasa.gov/climate", title="NASA evidence"),
    ]

    ranked = prioritize_candidates("Climate change is not real", candidates)

    assert ranked[0].url.host == "science.nasa.gov"
    assert [item.url.host for item in ranked].count("example.com") == 3
    assert ranked[-1].url.host == "facebook.com"


def test_claimed_social_platform_is_preserved_as_primary_evidence() -> None:
    candidates = [
        SearchResult(url="https://example.com/commentary", title="Commentary"),
        SearchResult(url="https://www.youtube.com/watch?v=claim", title="Claim video"),
    ]

    ranked = prioritize_candidates("A YouTube video claims the moon is artificial", candidates)

    assert ranked[0].url.host == "www.youtube.com"


def test_neutral_evidence_cannot_create_apparent_arguments() -> None:
    summary = InvestigationSummary(
        explanation="The available evidence is inconclusive.",
        pro_arguments=["Some theorists repeat the claim."],
        contra_arguments=["A critic disputes it."],
    )

    grounded = ground_summary_arguments(summary, [evidence(EvidencePosition.NEUTRAL)])

    assert grounded.pro_arguments == []
    assert grounded.contra_arguments == []


def test_grounded_side_is_preserved_while_missing_side_is_cleared() -> None:
    summary = InvestigationSummary(
        explanation="The claim is supported.",
        pro_arguments=["The research directly supports the claim."],
        contra_arguments=["Invented contrary argument."],
    )

    grounded = ground_summary_arguments(summary, [evidence(EvidencePosition.SUPPORTING)])

    assert grounded.pro_arguments == summary.pro_arguments
    assert grounded.contra_arguments == []

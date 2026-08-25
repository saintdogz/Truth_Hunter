"""Conservative search-candidate and result-summary quality gates."""

from app.investigation.models import (
    EvidenceAssessment,
    EvidencePosition,
    InvestigationSummary,
    SearchResult,
    SourceType,
)
from app.investigation.pipeline import (
    candidate_is_clearly_low_value,
    ground_summary_arguments,
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

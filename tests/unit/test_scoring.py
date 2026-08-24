"""Deterministic scoring, confidence, conflict, and verdict tests."""

from app.investigation.models import (
    ClaimType,
    Confidence,
    EvidenceAssessment,
    EvidencePosition,
    SourceType,
    Verdict,
)
from app.investigation.scoring import (
    DEFAULT_SCORING_CONFIG,
    apply_evidence_guardrails,
    calculate_balance,
    evidence_weight,
)
from app.investigation.verdict import calculate_assessment


def evidence(position: EvidencePosition, score: float = 0.9) -> EvidenceAssessment:
    return EvidenceAssessment(
        position=position,
        strength=score,
        relevance=score,
        quality=score,
        independence=score,
        recency=score,
        source_type=SourceType.PRIMARY_OFFICIAL,
        summary="Relevant evidence summary",
    )


def test_strong_supporting_evidence_produces_true() -> None:
    items = [evidence(EvidencePosition.SUPPORTING) for _ in range(5)]
    assessment = calculate_assessment(items, calculate_balance(items), ClaimType.FACTUAL)

    assert assessment.verdict == Verdict.TRUE
    assert assessment.confidence == Confidence.HIGH
    assert assessment.balance.supporting == 100


def test_strong_contradicting_evidence_produces_false() -> None:
    items = [evidence(EvidencePosition.CONTRADICTING) for _ in range(5)]
    assessment = calculate_assessment(items, calculate_balance(items), ClaimType.FACTUAL)

    assert assessment.verdict == Verdict.FALSE
    assert assessment.balance.contradicting == 100


def test_neutral_evidence_does_not_move_balance() -> None:
    items = [
        evidence(EvidencePosition.SUPPORTING),
        evidence(EvidencePosition.CONTRADICTING, 0.5),
        evidence(EvidencePosition.NEUTRAL),
    ]
    balance = calculate_balance(items)

    assert balance.supporting is not None
    assert balance.contradicting is not None
    assert balance.supporting + balance.contradicting == 100


def test_insufficient_evidence_overrides_numeric_score() -> None:
    items = [evidence(EvidencePosition.SUPPORTING)]
    assessment = calculate_assessment(items, calculate_balance(items), ClaimType.FACTUAL)

    assert assessment.balance.supporting == 100
    assert assessment.verdict == Verdict.INCONCLUSIVE


def test_opinion_is_not_assigned_objective_truth_verdict() -> None:
    items = [evidence(EvidencePosition.SUPPORTING) for _ in range(5)]
    assessment = calculate_assessment(items, calculate_balance(items), ClaimType.OPINION)

    assert assessment.verdict == Verdict.INCONCLUSIVE


def test_strong_evidence_on_both_sides_surfaces_conflict() -> None:
    items = [
        evidence(EvidencePosition.SUPPORTING),
        evidence(EvidencePosition.SUPPORTING),
        evidence(EvidencePosition.CONTRADICTING),
        evidence(EvidencePosition.CONTRADICTING),
    ]
    assessment = calculate_assessment(items, calculate_balance(items), ClaimType.FACTUAL)

    assert assessment.conflict.detected is True
    assert assessment.conflict.summary is not None


def test_official_qualification_contradicts_unconditional_claim() -> None:
    item = EvidenceAssessment(
        position=EvidencePosition.SUPPORTING,
        strength=0.7,
        relevance=0.9,
        quality=0.5,
        independence=0.5,
        recency=0.9,
        source_type=SourceType.SECONDARY,
        summary="Pilots may carry three passengers only after completing 10 PIC hours.",
    )

    guarded = apply_evidence_guardrails(
        "A LAPL(A) pilot may carry three passengers regardless of post-licence PIC hours.",
        item,
        "www.easa.europa.eu",
    )

    assert guarded.position == EvidencePosition.CONTRADICTING
    assert guarded.source_type == SourceType.PRIMARY_OFFICIAL
    assert guarded.quality == 0.9
    assert guarded.strength == 0.8


def test_authoritative_sources_outweigh_equivalent_secondary_sources() -> None:
    official = evidence(EvidencePosition.SUPPORTING)
    secondary = official.model_copy(update={"source_type": SourceType.SECONDARY})

    assert evidence_weight(official, DEFAULT_SCORING_CONFIG) > evidence_weight(
        secondary, DEFAULT_SCORING_CONFIG
    )

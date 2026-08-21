"""Deterministic scoring, confidence, conflict, and verdict tests."""

from app.investigation.models import (
    ClaimType,
    Confidence,
    EvidenceAssessment,
    EvidencePosition,
    SourceType,
    Verdict,
)
from app.investigation.scoring import calculate_balance
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

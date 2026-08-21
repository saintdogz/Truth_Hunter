"""Deterministic sufficiency, confidence, and verdict rules."""

from app.investigation.conflicts import detect_conflicts
from app.investigation.models import (
    AssessmentDraft,
    ClaimType,
    Confidence,
    EvidenceAssessment,
    EvidenceBalance,
    Verdict,
)


def evidence_is_sufficient(evidence: list[EvidenceAssessment], balance: EvidenceBalance) -> bool:
    relevant = [item for item in evidence if item.relevance >= 0.5 and item.quality >= 0.45]
    independent = sum(1 for item in relevant if item.independence >= 0.55)
    return balance.meaningful and len(relevant) >= 2 and independent >= 2


def calculate_confidence(
    evidence: list[EvidenceAssessment], balance: EvidenceBalance, conflict_level: float
) -> Confidence:
    relevant = [item for item in evidence if item.relevance >= 0.5]
    if not relevant or not balance.meaningful:
        return Confidence.LOW
    average_quality = sum(item.quality for item in relevant) / len(relevant)
    independent = sum(1 for item in relevant if item.independence >= 0.55)
    if len(relevant) >= 5 and average_quality >= 0.7 and independent >= 3 and conflict_level < 0.5:
        return Confidence.HIGH
    if len(relevant) >= 2 and average_quality >= 0.5 and independent >= 2:
        return Confidence.MEDIUM
    return Confidence.LOW


def determine_verdict(
    balance: EvidenceBalance,
    sufficient: bool,
    confidence: Confidence,
    claim_type: ClaimType,
) -> Verdict:
    if not sufficient or confidence == Confidence.LOW or not balance.meaningful:
        return Verdict.INCONCLUSIVE
    if claim_type == ClaimType.OPINION:
        return Verdict.INCONCLUSIVE
    supporting = balance.supporting
    if supporting is None:
        return Verdict.INCONCLUSIVE
    if supporting >= 85:
        return Verdict.TRUE
    if supporting >= 65:
        return Verdict.MOSTLY_TRUE
    if supporting >= 35:
        return Verdict.MIXED
    if supporting >= 15:
        return Verdict.MOSTLY_FALSE
    return Verdict.FALSE


def calculate_assessment(
    evidence: list[EvidenceAssessment], balance: EvidenceBalance, claim_type: ClaimType
) -> AssessmentDraft:
    conflict = detect_conflicts(evidence)
    sufficient = evidence_is_sufficient(evidence, balance)
    confidence = calculate_confidence(evidence, balance, conflict.level)
    verdict = determine_verdict(balance, sufficient, confidence, claim_type)
    return AssessmentDraft(
        verdict=verdict,
        balance=balance,
        confidence=confidence,
        conflict=conflict,
        evidence_sufficient=sufficient,
    )

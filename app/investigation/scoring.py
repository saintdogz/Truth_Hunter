"""Deterministic, versioned evidence balance calculation."""

from dataclasses import dataclass

from app.investigation.models import EvidenceAssessment, EvidenceBalance, EvidencePosition


@dataclass(frozen=True)
class ScoringConfig:
    version: str = "evidence-v1"
    strength_weight: float = 0.25
    relevance_weight: float = 0.30
    quality_weight: float = 0.20
    independence_weight: float = 0.15
    recency_weight: float = 0.10
    minimum_combined_weight: float = 0.35

    def __post_init__(self) -> None:
        total = (
            self.strength_weight
            + self.relevance_weight
            + self.quality_weight
            + self.independence_weight
            + self.recency_weight
        )
        if abs(total - 1.0) > 1e-9:
            raise ValueError("Evidence factor weights must total 1.0")


DEFAULT_SCORING_CONFIG = ScoringConfig()


def evidence_weight(item: EvidenceAssessment, config: ScoringConfig) -> float:
    """Combine independently assessed factors using application-owned constants."""

    return (
        item.strength * config.strength_weight
        + item.relevance * config.relevance_weight
        + item.quality * config.quality_weight
        + item.independence * config.independence_weight
        + item.recency * config.recency_weight
    )


def calculate_balance(
    evidence: list[EvidenceAssessment], config: ScoringConfig = DEFAULT_SCORING_CONFIG
) -> EvidenceBalance:
    supporting = sum(
        evidence_weight(item, config)
        for item in evidence
        if item.position == EvidencePosition.SUPPORTING
    )
    contradicting = sum(
        evidence_weight(item, config)
        for item in evidence
        if item.position == EvidencePosition.CONTRADICTING
    )
    combined = supporting + contradicting
    meaningful = combined >= config.minimum_combined_weight
    if not meaningful:
        return EvidenceBalance(
            supporting=None,
            contradicting=None,
            supporting_weight=supporting,
            contradicting_weight=contradicting,
            meaningful=False,
            scoring_version=config.version,
        )
    supporting_percent = round(supporting / combined * 100, 1)
    return EvidenceBalance(
        supporting=supporting_percent,
        contradicting=round(100 - supporting_percent, 1),
        supporting_weight=supporting,
        contradicting_weight=contradicting,
        meaningful=True,
        scoring_version=config.version,
    )

"""Deterministic, versioned evidence balance calculation."""

from dataclasses import dataclass

from app.investigation.models import (
    EvidenceAssessment,
    EvidenceBalance,
    EvidencePosition,
    SourceType,
)

AUTHORITATIVE_DOMAIN_SUFFIXES = ("easa.europa.eu", "eur-lex.europa.eu")
UNCONDITIONAL_CLAIM_MARKERS = (
    "regardless of",
    "irrespective of",
    "without exception",
    "függetlenül",
    "kivétel nélkül",
)
QUALIFICATION_MARKERS = (
    "only if",
    "only after",
    "except",
    "unless",
    "provided that",
    "subject to",
    "after completing",
    "required before",
    "csak akkor",
    "csak azt követően",
    "kivéve",
    "feltéve",
    "miután",
    "szükséges",
)
SOURCE_TYPE_MULTIPLIERS = {
    SourceType.PRIMARY_OFFICIAL: 1.15,
    SourceType.COURT_LEGAL: 1.15,
    SourceType.PRIMARY_RESEARCH: 1.10,
    SourceType.ACADEMIC: 1.05,
    SourceType.ESTABLISHED_MEDIA: 1.0,
    SourceType.EXPERT_ANALYSIS: 0.95,
    SourceType.SECONDARY: 0.85,
    SourceType.SOCIAL_MEDIA: 0.65,
    SourceType.UNKNOWN: 0.70,
}


@dataclass(frozen=True)
class ScoringConfig:
    version: str = "evidence-v2"
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
    """Combine assessed factors while giving primary evidence appropriate authority."""

    base_weight = (
        item.strength * config.strength_weight
        + item.relevance * config.relevance_weight
        + item.quality * config.quality_weight
        + item.independence * config.independence_weight
        + item.recency * config.recency_weight
    )
    return base_weight * SOURCE_TYPE_MULTIPLIERS[item.source_type]


def apply_evidence_guardrails(
    claim: str, item: EvidenceAssessment, source_domain: str
) -> EvidenceAssessment:
    """Correct narrow, high-impact evidence-labelling failures deterministically."""

    domain = source_domain.lower().rstrip(".")
    is_authoritative = any(
        domain == suffix or domain.endswith(f".{suffix}")
        for suffix in AUTHORITATIVE_DOMAIN_SUFFIXES
    )
    updates: dict[str, object] = {}
    if is_authoritative:
        updates.update(
            source_type=SourceType.PRIMARY_OFFICIAL,
            quality=max(item.quality, 0.9),
            independence=max(item.independence, 0.8),
        )

    claim_text = claim.casefold()
    evidence_text = " ".join((item.summary, item.excerpt, item.assessment)).casefold()
    has_unconditional_claim = any(marker in claim_text for marker in UNCONDITIONAL_CLAIM_MARKERS)
    has_material_qualification = any(marker in evidence_text for marker in QUALIFICATION_MARKERS)
    if (
        has_unconditional_claim
        and has_material_qualification
        and item.relevance >= 0.5
        and item.position != EvidencePosition.CONTRADICTING
    ):
        updates.update(
            position=EvidencePosition.CONTRADICTING,
            strength=max(item.strength, 0.8),
            relevance=max(item.relevance, 0.8),
        )

    return item.model_copy(update=updates) if updates else item


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

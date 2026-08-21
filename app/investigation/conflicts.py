"""Application-owned conflict detection."""

from app.investigation.models import (
    ConflictResult,
    EvidenceAssessment,
    EvidencePosition,
)
from app.investigation.scoring import DEFAULT_SCORING_CONFIG, evidence_weight


def detect_conflicts(evidence: list[EvidenceAssessment]) -> ConflictResult:
    strong_support = [
        item
        for item in evidence
        if item.position == EvidencePosition.SUPPORTING
        and evidence_weight(item, DEFAULT_SCORING_CONFIG) >= 0.6
    ]
    strong_contra = [
        item
        for item in evidence
        if item.position == EvidencePosition.CONTRADICTING
        and evidence_weight(item, DEFAULT_SCORING_CONFIG) >= 0.6
    ]
    detected = bool(strong_support and strong_contra)
    source_ids = [
        item.source_id for item in strong_support + strong_contra if item.source_id is not None
    ]
    level = min(1.0, min(len(strong_support), len(strong_contra)) / 2) if detected else 0.0
    return ConflictResult(
        detected=detected,
        summary=(
            "Credible evidence directly supports and contradicts the investigated claim."
            if detected
            else None
        ),
        conflicting_source_ids=source_ids,
        level=level,
    )

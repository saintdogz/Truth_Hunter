"""Deterministic, localized explanations for stored confidence levels."""

from collections.abc import Iterable
from typing import Protocol

from app.investigation.models import EvidencePosition


class EvidenceLike(Protocol):
    @property
    def position(self) -> str | EvidencePosition: ...

    @property
    def relevance(self) -> float: ...

    @property
    def quality(self) -> float: ...

    @property
    def independence(self) -> float: ...


def confidence_explanation(
    confidence: str,
    evidence: Iterable[EvidenceLike],
    *,
    conflict_detected: bool,
    language: str,
) -> str:
    relevant = [
        item
        for item in evidence
        if (item.position.value if isinstance(item.position, EvidencePosition) else item.position)
        != EvidencePosition.NEUTRAL.value
        and item.relevance >= 0.5
    ]
    independent = sum(item.independence >= 0.55 for item in relevant)
    average_quality = (
        round(sum(item.quality for item in relevant) / len(relevant) * 100) if relevant else 0
    )
    evidence_noun = "evidence item" if len(relevant) == 1 else "evidence items"

    if language == "hu":
        if confidence == "HIGH":
            return (
                f"Magas, mert {len(relevant)} releváns bizonyítékot értékeltünk, ezek közül "
                f"{independent} kellően független, az átlagos minőségük pedig {average_quality}%."
            )
        if confidence == "MEDIUM":
            conflict_note = " vagy érdemi ellentmondás maradt" if conflict_detected else ""
            return (
                f"Közepes, mert {len(relevant)} releváns és {independent} kellően független "
                "bizonyíték áll rendelkezésre, de a mennyiség, minőség vagy függetlenség nem "
                f"érte el a magas szint küszöbét{conflict_note}."
            )
        return (
            f"Alacsony, mert csak {len(relevant)} releváns és {independent} kellően független "
            "bizonyíték áll rendelkezésre; ez nem elég erős következtetéshez."
        )

    if confidence == "HIGH":
        return (
            f"High because {len(relevant)} relevant {evidence_noun} were assessed, {independent} "
            f"were sufficiently independent, and their average quality was {average_quality}%."
        )
    if confidence == "MEDIUM":
        conflict_note = " or meaningful disagreement remained" if conflict_detected else ""
        return (
            f"Medium because {len(relevant)} relevant {evidence_noun} and {independent} "
            "sufficiently independent evidence items were available, but their quantity, quality, "
            "or independence did not "
            f"meet the high-confidence threshold{conflict_note}."
        )
    return (
        f"Low because only {len(relevant)} relevant {evidence_noun} and {independent} sufficiently "
        "independent evidence items were available; that is not enough for a strong conclusion."
    )

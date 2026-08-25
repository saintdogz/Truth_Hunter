"""Plain-language confidence explanation tests."""

from dataclasses import dataclass

from app.web.confidence import confidence_explanation


@dataclass(frozen=True)
class Evidence:
    position: str
    relevance: float
    quality: float
    independence: float


def test_high_confidence_explains_reviewable_factors() -> None:
    items = [Evidence("SUPPORTING", 0.9, 0.8, 0.8) for _ in range(5)]

    explanation = confidence_explanation("HIGH", items, conflict_detected=False, language="en")

    assert "5 relevant evidence items" in explanation
    assert "5 were sufficiently independent" in explanation
    assert "80%" in explanation


def test_low_confidence_explanation_is_localized() -> None:
    explanation = confidence_explanation(
        "LOW",
        [Evidence("SUPPORTING", 0.2, 0.9, 0.9)],
        conflict_detected=False,
        language="hu",
    )

    assert "Alacsony" in explanation
    assert "0 releváns" in explanation


def test_neutral_items_do_not_inflate_or_reduce_confidence_factors() -> None:
    items = [
        Evidence("CONTRADICTING", 0.9, 0.8, 0.8),
        Evidence("NEUTRAL", 0.9, 0.1, 0.1),
    ]

    explanation = confidence_explanation("MEDIUM", items, conflict_detected=False, language="en")

    assert "1 relevant evidence item" in explanation

"""Claim validation and English/Hungarian language detection."""

from lingua import Language, LanguageDetectorBuilder

from app.investigation.models import ClaimInterpretation

MAX_CLAIM_LENGTH = 500

_detector = LanguageDetectorBuilder.from_languages(Language.ENGLISH, Language.HUNGARIAN).build()


class InvalidClaimError(ValueError):
    """Raised when submitted claim data is empty or outside MVP limits."""


def validate_claim(claim: str) -> str:
    """Validate without sanitizing or changing the original claim."""

    if not claim.strip():
        raise InvalidClaimError("Claim must not be empty")
    if len(claim) > MAX_CLAIM_LENGTH:
        raise InvalidClaimError(f"Claim must not exceed {MAX_CLAIM_LENGTH} characters")
    return claim


def detect_language(claim: str) -> str:
    """Detect one of the two MVP languages deterministically."""

    validate_claim(claim)
    detected = _detector.detect_language_of(claim)
    return "hu" if detected == Language.HUNGARIAN else "en"


def validate_interpretation(
    original_claim: str, interpretation: ClaimInterpretation
) -> ClaimInterpretation:
    """Apply application-owned limits to an AI-produced interpretation."""

    validate_claim(original_claim)
    validate_claim(interpretation.interpreted_claim)
    return interpretation

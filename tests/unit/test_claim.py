"""Claim boundary tests."""

import pytest

from app.investigation.claim import InvalidClaimError, detect_language, validate_claim


def test_original_claim_is_returned_exactly() -> None:
    claim = "  A strongly worded claim!  "
    assert validate_claim(claim) == claim


def test_empty_and_oversized_claims_are_rejected() -> None:
    with pytest.raises(InvalidClaimError):
        validate_claim("   ")
    with pytest.raises(InvalidClaimError):
        validate_claim("x" * 501)


def test_detects_supported_languages() -> None:
    assert detect_language("The government published a new official report.") == "en"
    assert detect_language("A kormány tegnap új hivatalos jelentést tett közzé.") == "hu"

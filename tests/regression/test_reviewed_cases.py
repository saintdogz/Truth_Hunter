"""Reviewed real-world claims that must not regress."""

import json
from pathlib import Path
from typing import Any, cast

import pytest

from app.investigation.models import (
    ClaimType,
    Confidence,
    EvidenceAssessment,
    EvidencePosition,
    SourceType,
    Verdict,
)
from app.investigation.scoring import apply_evidence_guardrails, calculate_balance
from app.investigation.verdict import calculate_assessment

CASES_PATH = Path(__file__).with_name("cases.json")


def reviewed_cases() -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], json.loads(CASES_PATH.read_text(encoding="utf-8")))


@pytest.mark.parametrize("case", reviewed_cases(), ids=lambda case: str(case["id"]))
def test_reviewed_claim(case: dict[str, Any]) -> None:
    evidence = []
    for source in case["evidence"]:
        item = EvidenceAssessment(
            position=EvidencePosition(source.get("position", "SUPPORTING")),
            strength=source.get("strength", 0.85),
            relevance=source.get("relevance", 0.9),
            quality=source.get("quality", 0.85),
            independence=source.get("independence", 0.8),
            recency=source.get("recency", 0.9),
            source_type=SourceType(source["source_type"]),
            summary=source["summary"],
        )
        evidence.append(apply_evidence_guardrails(case["claim"], item, source["domain"]))

    assessment = calculate_assessment(
        evidence,
        calculate_balance(evidence),
        ClaimType.FACTUAL,
    )

    assert assessment.verdict == Verdict(case["expected_verdict"])
    assert assessment.confidence == Confidence(case["expected_confidence"])

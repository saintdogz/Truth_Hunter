"""AI provider boundary owned by the Truth Hunter application."""

from typing import Protocol

from app.investigation.models import (
    AssessmentDraft,
    ClaimInterpretation,
    EvidenceAssessment,
    InvestigationSummary,
    SearchQueries,
    SourceDocument,
)


class AIProviderError(RuntimeError):
    """Sanitized provider failure exposed to pipeline orchestration."""


class AIProvider(Protocol):
    model_name: str

    async def interpret_claim(self, claim: str, detected_language: str) -> ClaimInterpretation: ...

    async def generate_search_queries(
        self, claim: str, detected_language: str
    ) -> SearchQueries: ...

    async def evaluate_evidence(self, claim: str, source: SourceDocument) -> EvidenceAssessment: ...

    async def generate_summary(
        self,
        claim: str,
        assessment: AssessmentDraft,
        evidence: list[EvidenceAssessment],
        language: str,
    ) -> InvestigationSummary: ...

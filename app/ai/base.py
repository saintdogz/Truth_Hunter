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

    def __init__(
        self,
        message: str,
        *,
        category: str = "provider_error",
        retryable: bool = False,
        permits_paid_fallback: bool = False,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.retryable = retryable
        self.permits_paid_fallback = permits_paid_fallback


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

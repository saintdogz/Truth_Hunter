"""Automatic operation-level fallback for configured AI providers."""

from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.ai.base import AIProvider, AIProviderError
from app.investigation.models import (
    AssessmentDraft,
    ClaimInterpretation,
    EvidenceAssessment,
    InvestigationSummary,
    SearchQueries,
    SourceDocument,
)

Result = TypeVar("Result")


class FallbackAIProvider:
    """Use the fallback only after the primary reports a sanitized failure."""

    def __init__(
        self,
        primary: AIProvider,
        fallback: AIProvider,
        *,
        primary_label: str,
        fallback_label: str,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._primary_name = f"{primary_label}/{primary.model_name}"
        self._fallback_name = f"{fallback_label}/{fallback.model_name}"
        self.model_name = self._primary_name

    async def close(self) -> None:
        for provider in (self._primary, self._fallback):
            close = getattr(provider, "close", None)
            if close is not None:
                await close()

    async def _run(
        self,
        primary_call: Callable[[], Awaitable[Result]],
        fallback_call: Callable[[], Awaitable[Result]],
    ) -> Result:
        try:
            return await primary_call()
        except AIProviderError:
            result = await fallback_call()
            self.model_name = f"{self._primary_name} → {self._fallback_name}"
            return result

    async def interpret_claim(self, claim: str, detected_language: str) -> ClaimInterpretation:
        return await self._run(
            lambda: self._primary.interpret_claim(claim, detected_language),
            lambda: self._fallback.interpret_claim(claim, detected_language),
        )

    async def generate_search_queries(self, claim: str, detected_language: str) -> SearchQueries:
        return await self._run(
            lambda: self._primary.generate_search_queries(claim, detected_language),
            lambda: self._fallback.generate_search_queries(claim, detected_language),
        )

    async def evaluate_evidence(self, claim: str, source: SourceDocument) -> EvidenceAssessment:
        return await self._run(
            lambda: self._primary.evaluate_evidence(claim, source),
            lambda: self._fallback.evaluate_evidence(claim, source),
        )

    async def generate_summary(
        self,
        claim: str,
        assessment: AssessmentDraft,
        evidence: list[EvidenceAssessment],
        language: str,
    ) -> InvestigationSummary:
        return await self._run(
            lambda: self._primary.generate_summary(claim, assessment, evidence, language),
            lambda: self._fallback.generate_summary(claim, assessment, evidence, language),
        )

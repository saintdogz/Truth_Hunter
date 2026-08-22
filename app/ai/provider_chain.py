"""Ordered free-first AI provider chain with explicit paid-fallback controls."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic
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

COOLDOWN_SECONDS = {
    "availability": 15.0,
    "model_output": 30.0,
    "payload_too_large": 300.0,
    "quota": 300.0,
    "rate_limit": 60.0,
}


@dataclass(frozen=True)
class ProviderEntry:
    name: str
    provider: AIProvider
    paid: bool = False


class ProviderChain:
    """Try configured free providers first and tightly gate paid fallback."""

    def __init__(
        self,
        entries: list[ProviderEntry],
        *,
        allow_paid_fallback: bool,
        max_paid_calls: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not entries:
            raise ValueError("At least one AI provider must be configured")
        self._entries = entries
        self._allow_paid_fallback = allow_paid_fallback
        self._max_paid_calls = max_paid_calls
        self._paid_calls = 0
        self._clock = clock
        self._cooldowns: dict[str, tuple[float, AIProviderError]] = {}
        self.attempts: list[dict[str, object]] = []
        first = entries[0]
        self.model_name = f"{first.name}/{first.provider.model_name}"

    async def close(self) -> None:
        for entry in self._entries:
            close = getattr(entry.provider, "close", None)
            if close is not None:
                await close()

    async def _run(
        self,
        operation: str,
        make_call: Callable[[AIProvider], Awaitable[Result]],
    ) -> Result:
        free_errors: list[AIProviderError] = []
        last_error: AIProviderError | None = None

        for entry in self._entries:
            cooldown = self._cooldowns.get(entry.name)
            if cooldown is not None and cooldown[0] > self._clock():
                error = cooldown[1]
                if not entry.paid:
                    free_errors.append(error)
                self.attempts.append(
                    {
                        "operation": operation,
                        "provider": entry.name,
                        "model": entry.provider.model_name,
                        "tier": "paid" if entry.paid else "free",
                        "status": "cooldown",
                        "category": error.category,
                    }
                )
                continue
            if entry.paid:
                paid_is_safe = free_errors and all(
                    error.permits_paid_fallback for error in free_errors
                )
                if (
                    not self._allow_paid_fallback
                    or not paid_is_safe
                    or self._paid_calls >= self._max_paid_calls
                ):
                    continue
                self._paid_calls += 1
            try:
                result = await make_call(entry.provider)
            except AIProviderError as exc:
                last_error = exc
                cooldown_seconds = COOLDOWN_SECONDS.get(exc.category)
                if exc.retryable and cooldown_seconds is not None:
                    self._cooldowns[entry.name] = (
                        self._clock() + cooldown_seconds,
                        exc,
                    )
                if not entry.paid:
                    free_errors.append(exc)
                self.attempts.append(
                    {
                        "operation": operation,
                        "provider": entry.name,
                        "model": entry.provider.model_name,
                        "tier": "paid" if entry.paid else "free",
                        "status": "failed",
                        "category": exc.category,
                    }
                )
                continue

            self._cooldowns.pop(entry.name, None)
            self.model_name = f"{entry.name}/{entry.provider.model_name}"
            self.attempts.append(
                {
                    "operation": operation,
                    "provider": entry.name,
                    "model": entry.provider.model_name,
                    "tier": "paid" if entry.paid else "free",
                    "status": "succeeded",
                }
            )
            return result

        raise AIProviderError(
            "No configured AI provider could complete the request",
            category=last_error.category if last_error else "no_provider",
        ) from last_error

    async def interpret_claim(self, claim: str, detected_language: str) -> ClaimInterpretation:
        return await self._run(
            "interpret_claim",
            lambda provider: provider.interpret_claim(claim, detected_language),
        )

    async def generate_search_queries(self, claim: str, detected_language: str) -> SearchQueries:
        return await self._run(
            "generate_search_queries",
            lambda provider: provider.generate_search_queries(claim, detected_language),
        )

    async def evaluate_evidence(self, claim: str, source: SourceDocument) -> EvidenceAssessment:
        return await self._run(
            "evaluate_evidence",
            lambda provider: provider.evaluate_evidence(claim, source),
        )

    async def generate_summary(
        self,
        claim: str,
        assessment: AssessmentDraft,
        evidence: list[EvidenceAssessment],
        language: str,
    ) -> InvestigationSummary:
        return await self._run(
            "generate_summary",
            lambda provider: provider.generate_summary(claim, assessment, evidence, language),
        )

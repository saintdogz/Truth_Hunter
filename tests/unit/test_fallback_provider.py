"""Automatic AI provider fallback tests."""

from typing import Any

import pytest

from app.ai.base import AIProviderError
from app.ai.fallback_provider import FallbackAIProvider
from app.investigation.models import ClaimInterpretation


class FakeProvider:
    def __init__(self, model_name: str, *, fails: bool) -> None:
        self.model_name = model_name
        self.fails = fails
        self.calls = 0

    async def interpret_claim(self, claim: str, detected_language: str) -> ClaimInterpretation:
        self.calls += 1
        if self.fails:
            raise AIProviderError("sanitized failure")
        return ClaimInterpretation(
            interpreted_claim=claim,
            language="en",
            claim_type="factual",
            confidence=0.8,
        )

    async def generate_search_queries(self, claim: str, detected_language: str) -> Any:
        raise NotImplementedError

    async def evaluate_evidence(self, claim: str, source: Any) -> Any:
        raise NotImplementedError

    async def generate_summary(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError


@pytest.mark.anyio
async def test_fallback_is_not_called_when_primary_succeeds() -> None:
    primary = FakeProvider("primary-model", fails=False)
    fallback = FakeProvider("fallback-model", fails=False)
    provider = FallbackAIProvider(
        primary, fallback, primary_label="groq", fallback_label="deepseek"
    )

    await provider.interpret_claim("A claim", "en")

    assert primary.calls == 1
    assert fallback.calls == 0
    assert provider.model_name == "groq/primary-model"


@pytest.mark.anyio
async def test_sanitized_primary_failure_uses_and_records_fallback() -> None:
    primary = FakeProvider("primary-model", fails=True)
    fallback = FakeProvider("fallback-model", fails=False)
    provider = FallbackAIProvider(
        primary, fallback, primary_label="groq", fallback_label="deepseek"
    )

    result = await provider.interpret_claim("A claim", "en")

    assert result.interpreted_claim == "A claim"
    assert primary.calls == 1
    assert fallback.calls == 1
    assert provider.model_name == "groq/primary-model → deepseek/fallback-model"

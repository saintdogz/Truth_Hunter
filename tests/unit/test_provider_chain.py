"""Tier-aware ordered AI provider chain tests."""

from typing import Any

import pytest

from app.ai.base import AIProviderError
from app.ai.provider_chain import ProviderChain, ProviderEntry
from app.investigation.models import ClaimInterpretation


class FakeProvider:
    def __init__(
        self,
        model_name: str,
        *,
        error: AIProviderError | None = None,
    ) -> None:
        self.model_name = model_name
        self.error = error
        self.calls = 0

    async def interpret_claim(self, claim: str, detected_language: str) -> ClaimInterpretation:
        self.calls += 1
        if self.error:
            raise self.error
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


def quota_error() -> AIProviderError:
    return AIProviderError(
        "quota exhausted",
        category="quota",
        retryable=True,
        permits_paid_fallback=True,
    )


@pytest.mark.anyio
async def test_chain_uses_first_successful_free_provider() -> None:
    groq = FakeProvider("groq-model", error=quota_error())
    gemini = FakeProvider("gemini-model")
    deepseek = FakeProvider("deepseek-model")
    chain = ProviderChain(
        [
            ProviderEntry("groq", groq),
            ProviderEntry("gemini", gemini),
            ProviderEntry("deepseek", deepseek, paid=True),
        ],
        allow_paid_fallback=True,
        max_paid_calls=10,
    )

    await chain.interpret_claim("A claim", "en")

    assert groq.calls == 1
    assert gemini.calls == 1
    assert deepseek.calls == 0
    assert chain.model_name == "gemini/gemini-model"


@pytest.mark.anyio
async def test_paid_fallback_requires_explicit_opt_in() -> None:
    groq = FakeProvider("groq-model", error=quota_error())
    deepseek = FakeProvider("deepseek-model")
    chain = ProviderChain(
        [
            ProviderEntry("groq", groq),
            ProviderEntry("deepseek", deepseek, paid=True),
        ],
        allow_paid_fallback=False,
        max_paid_calls=10,
    )

    with pytest.raises(AIProviderError, match="No configured"):
        await chain.interpret_claim("A claim", "en")

    assert deepseek.calls == 0


@pytest.mark.anyio
async def test_configuration_failure_never_triggers_paid_fallback() -> None:
    invalid_key = AIProviderError("invalid key", category="configuration")
    groq = FakeProvider("groq-model", error=invalid_key)
    deepseek = FakeProvider("deepseek-model")
    chain = ProviderChain(
        [
            ProviderEntry("groq", groq),
            ProviderEntry("deepseek", deepseek, paid=True),
        ],
        allow_paid_fallback=True,
        max_paid_calls=10,
    )

    with pytest.raises(AIProviderError, match="No configured"):
        await chain.interpret_claim("A claim", "en")

    assert deepseek.calls == 0


@pytest.mark.anyio
async def test_all_free_quota_failures_allow_bounded_paid_fallback() -> None:
    groq = FakeProvider("groq-model", error=quota_error())
    gemini = FakeProvider("gemini-model", error=quota_error())
    deepseek = FakeProvider("deepseek-model")
    chain = ProviderChain(
        [
            ProviderEntry("groq", groq),
            ProviderEntry("gemini", gemini),
            ProviderEntry("deepseek", deepseek, paid=True),
        ],
        allow_paid_fallback=True,
        max_paid_calls=1,
    )

    await chain.interpret_claim("A claim", "en")

    assert deepseek.calls == 1
    assert chain.model_name == "deepseek/deepseek-model"
    assert chain.attempts[-1]["tier"] == "paid"

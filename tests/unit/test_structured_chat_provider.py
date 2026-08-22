"""Regression tests for malformed OpenAI-compatible provider responses."""

from types import SimpleNamespace
from typing import Any

import pytest

from app.ai.base import AIProviderError
from app.ai.structured_chat_provider import StructuredChatProvider


class MissingMessageCompletions:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        del kwargs
        self.calls += 1
        return SimpleNamespace(choices=[SimpleNamespace(message=None)])


class MissingMessageClient:
    def __init__(self) -> None:
        self.completions = MissingMessageCompletions()
        self.chat = SimpleNamespace(completions=self.completions)


@pytest.mark.anyio
async def test_missing_message_is_a_sanitized_retryable_error() -> None:
    client = MissingMessageClient()
    provider = StructuredChatProvider(
        provider_name="gemini",
        api_key="test-key",
        model="test-model",
        base_url="https://example.invalid",
        client=client,  # type: ignore[arg-type]
        validation_attempts=2,
    )

    with pytest.raises(AIProviderError) as raised:
        await provider.interpret_claim("A test claim", "en")

    assert raised.value.category == "model_output"
    assert raised.value.retryable is True
    assert client.completions.calls == 2

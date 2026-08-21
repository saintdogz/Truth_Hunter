"""Groq strict structured-output adapter."""

from openai import AsyncOpenAI

from app.ai.structured_chat_provider import StructuredChatProvider


class GroqProvider(StructuredChatProvider):
    def __init__(
        self,
        api_key: str,
        model: str,
        client: AsyncOpenAI | None = None,
        validation_attempts: int = 3,
    ) -> None:
        super().__init__(
            provider_name="groq",
            api_key=api_key,
            model=model,
            base_url="https://api.groq.com/openai/v1",
            client=client,
            validation_attempts=validation_attempts,
        )

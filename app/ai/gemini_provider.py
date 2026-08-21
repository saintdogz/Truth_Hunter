"""Gemini free-tier adapter through Google's OpenAI-compatible endpoint."""

from app.ai.structured_chat_provider import StructuredChatProvider


class GeminiProvider(StructuredChatProvider):
    def __init__(self, api_key: str, model: str) -> None:
        super().__init__(
            provider_name="gemini",
            api_key=api_key,
            model=model,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )

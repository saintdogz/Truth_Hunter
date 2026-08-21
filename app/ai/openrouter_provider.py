"""OpenRouter free-model adapter with structured-output routing requirements."""

from app.ai.structured_chat_provider import StructuredChatProvider


class OpenRouterProvider(StructuredChatProvider):
    def __init__(self, api_key: str, model: str) -> None:
        super().__init__(
            provider_name="openrouter",
            api_key=api_key,
            model=model,
            base_url="https://openrouter.ai/api/v1",
            extra_body={"provider": {"require_parameters": True}},
        )

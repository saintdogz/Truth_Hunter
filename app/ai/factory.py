"""Configured AI provider construction."""

from app.ai.base import AIProvider
from app.ai.openai_provider import OpenAIProvider
from app.core.config import Settings


def create_ai_provider(settings: Settings) -> AIProvider:
    if settings.ai_provider != "openai":
        raise ValueError(f"Unsupported AI provider: {settings.ai_provider}")
    if settings.ai_api_key is None:
        raise ValueError("AI_API_KEY is required to run investigations")
    return OpenAIProvider(settings.ai_api_key.get_secret_value(), settings.ai_model)

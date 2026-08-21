"""Configured AI provider construction."""

from app.ai.base import AIProvider
from app.ai.deepseek_provider import DeepSeekProvider
from app.ai.openai_provider import OpenAIProvider
from app.core.config import Settings


def create_ai_provider(settings: Settings) -> AIProvider:
    if settings.ai_api_key is None:
        raise ValueError("AI_API_KEY is required to run investigations")
    api_key = settings.ai_api_key.get_secret_value()
    if settings.ai_provider == "openai":
        return OpenAIProvider(api_key, settings.ai_model)
    if settings.ai_provider == "deepseek":
        return DeepSeekProvider(api_key, settings.ai_model)
    raise ValueError(f"Unsupported AI provider: {settings.ai_provider}")

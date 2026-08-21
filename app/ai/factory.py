"""Configured AI provider construction."""

from app.ai.base import AIProvider
from app.ai.deepseek_provider import DeepSeekProvider
from app.ai.fallback_provider import FallbackAIProvider
from app.ai.groq_provider import GroqProvider
from app.ai.openai_provider import OpenAIProvider
from app.core.config import Settings


def _create_provider(provider: str, api_key: str, model: str) -> AIProvider:
    if provider == "openai":
        return OpenAIProvider(api_key, model)
    if provider == "deepseek":
        return DeepSeekProvider(api_key, model)
    if provider == "groq":
        return GroqProvider(api_key, model)
    raise ValueError(f"Unsupported AI provider: {provider}")


def create_ai_provider(settings: Settings) -> AIProvider:
    if settings.ai_api_key is None:
        raise ValueError("AI_API_KEY is required to run investigations")
    primary = _create_provider(
        settings.ai_provider,
        settings.ai_api_key.get_secret_value(),
        settings.ai_model,
    )
    if (
        settings.ai_fallback_provider is None
        or settings.ai_fallback_api_key is None
        or settings.ai_fallback_model is None
    ):
        return primary
    fallback = _create_provider(
        settings.ai_fallback_provider,
        settings.ai_fallback_api_key.get_secret_value(),
        settings.ai_fallback_model,
    )
    return FallbackAIProvider(
        primary,
        fallback,
        primary_label=settings.ai_provider,
        fallback_label=settings.ai_fallback_provider,
    )

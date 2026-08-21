"""Registry-based ordered AI provider construction."""

from collections.abc import Callable

from pydantic import SecretStr

from app.ai.base import AIProvider
from app.ai.deepseek_provider import DeepSeekProvider
from app.ai.gemini_provider import GeminiProvider
from app.ai.groq_provider import GroqProvider
from app.ai.openai_provider import OpenAIProvider
from app.ai.openrouter_provider import OpenRouterProvider
from app.ai.provider_chain import ProviderChain, ProviderEntry
from app.core.config import Settings

ProviderBuilder = Callable[[str, str], AIProvider]

PROVIDER_BUILDERS: dict[str, ProviderBuilder] = {
    "openai": OpenAIProvider,
    "deepseek": DeepSeekProvider,
    "groq": GroqProvider,
    "gemini": GeminiProvider,
    "openrouter": OpenRouterProvider,
}
PAID_PROVIDERS = {"openai", "deepseek"}


def _secret_value(secret: SecretStr | None) -> str | None:
    return secret.get_secret_value() if secret is not None else None


def _provider_credentials(settings: Settings, name: str) -> tuple[str | None, str]:
    key = _secret_value(getattr(settings, f"{name}_api_key", None))
    model = getattr(settings, f"{name}_model", settings.ai_model)
    if key is None and name == settings.ai_provider:
        key = _secret_value(settings.ai_api_key)
        model = settings.ai_model
    if key is None and name == settings.ai_fallback_provider:
        key = _secret_value(settings.ai_fallback_api_key)
        model = settings.ai_fallback_model or model
    return key, model


def create_ai_provider(settings: Settings) -> AIProvider:
    entries: list[ProviderEntry] = []
    for name in settings.provider_order:
        key, model = _provider_credentials(settings, name)
        if key is None:
            continue
        paid = name in PAID_PROVIDERS
        if paid and not settings.allow_paid_ai_fallback:
            continue
        entries.append(ProviderEntry(name, PROVIDER_BUILDERS[name](key, model), paid=paid))

    if not entries:
        raise ValueError("No enabled AI provider has a configured API key")
    return ProviderChain(
        entries,
        allow_paid_fallback=settings.allow_paid_ai_fallback,
        max_paid_calls=settings.ai_max_paid_fallback_calls,
    )

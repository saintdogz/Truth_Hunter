"""Sanitized classification for OpenAI-compatible provider failures."""

from openai import OpenAIError

from app.ai.base import AIProviderError


def classify_provider_error(provider: str, exc: OpenAIError) -> AIProviderError:
    status = getattr(exc, "status_code", None)
    if status in {402, 429}:
        category = "quota" if status == 402 else "rate_limit"
        return AIProviderError(
            f"The {provider} provider is temporarily unavailable",
            category=category,
            retryable=True,
            permits_paid_fallback=True,
        )
    if status == 413:
        return AIProviderError(
            f"The {provider} provider rejected an oversized request",
            category="payload_too_large",
            retryable=True,
            permits_paid_fallback=True,
        )
    if status == 422:
        return AIProviderError(
            f"The {provider} provider rejected a generated response",
            category="model_output",
            retryable=True,
            permits_paid_fallback=True,
        )
    if status is not None and status >= 500:
        return AIProviderError(
            f"The {provider} provider is temporarily unavailable",
            category="availability",
            retryable=True,
            permits_paid_fallback=True,
        )
    if status is None:
        return AIProviderError(
            f"The {provider} provider could not be reached",
            category="availability",
            retryable=True,
            permits_paid_fallback=True,
        )
    return AIProviderError(
        f"The {provider} provider configuration or request was rejected",
        category="configuration",
    )

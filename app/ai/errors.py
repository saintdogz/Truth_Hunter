"""Typed, sanitized classification for OpenAI-compatible provider failures."""

from openai import OpenAIError

from app.ai.base import AIProviderError


class RateLimitError(AIProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            f"The {provider} provider is temporarily rate limited",
            category="rate_limit",
            retryable=True,
            permits_paid_fallback=True,
        )


class QuotaExhaustedError(AIProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            f"The {provider} provider quota is unavailable",
            category="quota",
            retryable=True,
            permits_paid_fallback=True,
        )


class ProviderUnavailableError(AIProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            f"The {provider} provider is temporarily unavailable",
            category="availability",
            retryable=True,
            permits_paid_fallback=True,
        )


class PayloadTooLargeError(AIProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            f"The {provider} provider rejected an oversized request",
            category="payload_too_large",
            retryable=True,
            permits_paid_fallback=True,
        )


class ModelOutputError(AIProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            f"The {provider} provider returned invalid structured output",
            category="model_output",
            retryable=True,
            permits_paid_fallback=True,
        )


class ProviderConfigurationError(AIProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            f"The {provider} provider configuration or request was rejected",
            category="configuration",
        )


def classify_provider_error(provider: str, exc: OpenAIError) -> AIProviderError:
    status = getattr(exc, "status_code", None)
    message = str(exc).casefold()
    if status == 402 or (status == 429 and any(word in message for word in ("quota", "credit"))):
        return QuotaExhaustedError(provider)
    if status == 429:
        return RateLimitError(provider)
    if status == 413:
        return PayloadTooLargeError(provider)
    if status == 422:
        return ModelOutputError(provider)
    if status is not None and status >= 500:
        return ProviderUnavailableError(provider)
    if status is None:
        return ProviderUnavailableError(provider)
    return ProviderConfigurationError(provider)

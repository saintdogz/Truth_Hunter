"""Provider failure taxonomy regression tests."""

from typing import Any, cast

from openai import OpenAIError

from app.ai.base import AIProviderError
from app.ai.errors import (
    ProviderConfigurationError,
    ProviderUnavailableError,
    QuotaExhaustedError,
    RateLimitError,
    classify_provider_error,
)


class FakeOpenAIError(Exception):
    def __init__(self, status_code: int | None, message: str = "failure") -> None:
        super().__init__(message)
        self.status_code = status_code


def classify(status: int | None, message: str = "failure") -> AIProviderError:
    error = cast(OpenAIError, cast(Any, FakeOpenAIError(status, message)))
    return classify_provider_error("test", error)


def test_rate_limit_is_distinct_from_quota_exhaustion() -> None:
    assert isinstance(classify(429, "requests per minute exceeded"), RateLimitError)
    assert isinstance(classify(429, "insufficient quota"), QuotaExhaustedError)
    assert isinstance(classify(402), QuotaExhaustedError)


def test_availability_and_configuration_failures_have_different_policy() -> None:
    unavailable = classify(503)
    configuration = classify(401)

    assert isinstance(unavailable, ProviderUnavailableError)
    assert unavailable.retryable is True
    assert unavailable.permits_paid_fallback is True
    assert isinstance(configuration, ProviderConfigurationError)
    assert configuration.retryable is False
    assert configuration.permits_paid_fallback is False

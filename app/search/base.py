"""Replaceable web search boundary."""

from typing import Protocol

from app.investigation.models import SearchResult


class SearchProviderError(RuntimeError):
    """Sanitized search failure carrying orchestration policy."""

    def __init__(self, message: str, *, category: str, retryable: bool) -> None:
        super().__init__(message)
        self.category = category
        self.retryable = retryable


class SearchRateLimitError(SearchProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            f"{provider} search is temporarily rate limited",
            category="rate_limit",
            retryable=True,
        )


class SearchQuotaError(SearchProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            f"{provider} search quota is unavailable",
            category="quota",
            retryable=False,
        )


class SearchAuthenticationError(SearchProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            f"{provider} search authentication failed",
            category="authentication",
            retryable=False,
        )


class SearchUnavailableError(SearchProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            f"{provider} search is temporarily unavailable",
            category="availability",
            retryable=True,
        )


class SearchResponseError(SearchProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            f"{provider} search returned an invalid response",
            category="invalid_response",
            retryable=True,
        )


class SearchProvider(Protocol):
    provider_name: str

    async def search(self, query: str, language: str, limit: int) -> list[SearchResult]: ...

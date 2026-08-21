"""Replaceable web search boundary."""

from typing import Protocol

from app.investigation.models import SearchResult


class SearchProviderError(RuntimeError):
    """Sanitized search provider failure."""


class SearchProvider(Protocol):
    provider_name: str

    async def search(self, query: str, language: str, limit: int) -> list[SearchResult]: ...

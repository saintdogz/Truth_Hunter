"""Self-hosted SearXNG JSON API adapter."""

import httpx
from pydantic import ValidationError

from app.investigation.models import SearchResult
from app.search.base import (
    SearchRateLimitError,
    SearchResponseError,
    SearchUnavailableError,
)


class SearXNGProvider:
    provider_name = "searxng"

    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=20, trust_env=False)
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(self, query: str, language: str, limit: int) -> list[SearchResult]:
        if not query.strip():
            return []
        try:
            response = await self._client.get(
                f"{self._base_url}/search",
                params={"q": query, "language": language, "format": "json", "safesearch": 0},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise SearchRateLimitError("SearXNG") from exc
            raise SearchUnavailableError("SearXNG") from exc
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise SearchUnavailableError("SearXNG") from exc
        except ValueError as exc:
            raise SearchResponseError("SearXNG") from exc

        if not payload.get("results") and payload.get("unresponsive_engines"):
            raise SearchUnavailableError("SearXNG engines")

        results: list[SearchResult] = []
        for raw in payload.get("results", []):
            try:
                results.append(
                    SearchResult(
                        url=raw.get("url", ""),
                        title=raw.get("title", "")[:500],
                        snippet=raw.get("content", "")[:2000],
                        engine=raw.get("engine"),
                    )
                )
            except ValidationError:
                continue
            if len(results) >= limit:
                break
        return results

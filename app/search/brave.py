"""Official Brave Web Search API adapter used as a metered fallback."""

import httpx
from pydantic import ValidationError

from app.investigation.models import SearchResult
from app.search.base import SearchProviderError


class BraveSearchProvider:
    provider_name = "brave"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.search.brave.com/res/v1/web/search",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("A Brave Search API key is required")
        self._api_key = api_key
        self._base_url = base_url
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
                self._base_url,
                params={
                    "q": query,
                    "count": min(limit, 20),
                    "search_lang": language,
                    "safesearch": "off",
                },
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": self._api_key,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SearchProviderError("Brave Search API failed") from exc

        results: list[SearchResult] = []
        for raw in payload.get("web", {}).get("results", []):
            try:
                results.append(
                    SearchResult(
                        url=raw.get("url", ""),
                        title=raw.get("title", "")[:500],
                        snippet=raw.get("description", "")[:2000],
                        engine="brave-api",
                    )
                )
            except ValidationError:
                continue
            if len(results) >= limit:
                break
        return results

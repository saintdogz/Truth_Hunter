"""SearXNG provider contract tests."""

import httpx
import pytest

from app.search.base import SearchProviderError
from app.search.brave import BraveSearchProvider
from app.search.searxng import SearXNGProvider


@pytest.mark.anyio
async def test_searxng_maps_and_limits_valid_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["format"] == "json"
        assert request.url.params["language"] == "hu"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://example.com/one",
                        "title": "One",
                        "content": "Evidence one",
                        "engine": "test",
                    },
                    {"url": "not a url", "title": "Invalid"},
                    {"url": "https://example.com/two", "title": "Two"},
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = SearXNGProvider("http://searxng:8080", client)
    results = await provider.search("állítás", "hu", 2)

    assert [result.title for result in results] == ["One", "Two"]
    await client.aclose()


@pytest.mark.anyio
async def test_searxng_surfaces_engine_outage_when_results_are_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={"results": [], "unresponsive_engines": [["duckduckgo", "CAPTCHA"]]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = SearXNGProvider("http://searxng:8080", client)

    with pytest.raises(SearchProviderError, match="engines were unavailable"):
        await provider.search("claim", "en", 8)
    await client.aclose()


@pytest.mark.anyio
async def test_brave_maps_results_and_authenticates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Subscription-Token"] == "test-key"
        assert request.url.params["search_lang"] == "en"
        assert request.url.params["count"] == "2"
        return httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {
                            "url": "https://evidence.example/one",
                            "title": "Evidence one",
                            "description": "Relevant source",
                        },
                        {"url": "not-a-url", "title": "Invalid"},
                        {"url": "https://evidence.example/two", "title": "Evidence two"},
                    ]
                }
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = BraveSearchProvider("test-key", client=client)

    results = await provider.search("claim evidence", "en", 2)

    assert [result.title for result in results] == ["Evidence one", "Evidence two"]
    assert {result.engine for result in results} == {"brave-api"}
    await client.aclose()

"""SearXNG provider contract tests."""

import httpx
import pytest

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

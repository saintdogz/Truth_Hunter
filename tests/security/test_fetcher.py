"""SSRF and bounded source extraction tests."""

import ipaddress

import httpx
import pytest

from app.investigation import fetcher as fetcher_module
from app.investigation.fetcher import FetchPolicy, SafeSourceFetcher, UnsafeUrlError
from app.investigation.models import SearchResult


@pytest.mark.anyio
async def test_private_ip_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fetcher_module,
        "_resolve_addresses",
        lambda hostname, port: {ipaddress.ip_address("127.0.0.1")},
    )
    with pytest.raises(UnsafeUrlError):
        await fetcher_module.validate_public_url("http://example.test/private")


@pytest.mark.anyio
async def test_redirect_target_is_revalidated(monkeypatch: pytest.MonkeyPatch) -> None:
    def addresses(hostname: str, port: int):  # type: ignore[no-untyped-def]
        del port
        return {
            ipaddress.ip_address("127.0.0.1" if hostname == "internal.test" else "93.184.216.34")
        }

    monkeypatch.setattr(fetcher_module, "_resolve_addresses", addresses)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://internal.test/secret"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    source_fetcher = SafeSourceFetcher(client=client)
    with pytest.raises(UnsafeUrlError):
        await source_fetcher.fetch(SearchResult(url="https://public.test/article"))
    await client.aclose()


@pytest.mark.anyio
async def test_html_is_safely_extracted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fetcher_module,
        "_resolve_addresses",
        lambda hostname, port: {ipaddress.ip_address("93.184.216.34")},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=(
                b"<html><title>Evidence</title><script>ignore()</script><p>Useful text</p></html>"
            ),
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    source_fetcher = SafeSourceFetcher(FetchPolicy(max_bytes=1_000), client)
    document = await source_fetcher.fetch(SearchResult(url="https://public.test/article"))

    assert document.title == "Evidence"
    assert document.text == "Evidence Useful text"
    assert "ignore" not in document.text
    await client.aclose()

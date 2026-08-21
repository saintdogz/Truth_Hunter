"""Hostile-URL-aware text fetcher with bounded extraction."""

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from app.investigation.models import SearchResult, SourceDocument

ALLOWED_CONTENT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")


class UnsafeUrlError(ValueError):
    """Raised when a URL could reach a private or non-web destination."""


class SourceFetchError(RuntimeError):
    """Sanitized source retrieval or extraction failure."""


@dataclass(frozen=True)
class FetchPolicy:
    timeout_seconds: float = 15
    max_bytes: int = 2_000_000
    redirect_limit: int = 4


def _resolve_addresses(
    hostname: str, port: int
) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError("URL hostname could not be resolved") from exc
    return {ipaddress.ip_address(record[4][0]) for record in records}


async def validate_public_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrlError("Only absolute HTTP(S) URLs are allowed")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URLs containing credentials are not allowed")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
        raise UnsafeUrlError("Internal hostnames are not allowed")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = await asyncio.to_thread(_resolve_addresses, hostname, port)
    if not addresses or any(not address.is_global for address in addresses):
        raise UnsafeUrlError("Private, loopback, link-local, or reserved addresses are not allowed")


def _extract_text(content: bytes, content_type: str) -> tuple[str, str]:
    decoded = content.decode("utf-8", errors="replace")
    if content_type.startswith("text/plain"):
        return "", " ".join(decoded.split())
    soup = BeautifulSoup(decoded, "html.parser")
    for element in soup(["script", "style", "noscript", "svg", "template"]):
        element.decompose()
    title = soup.title.get_text(" ", strip=True)[:500] if soup.title else ""
    text = " ".join(soup.get_text(" ", strip=True).split())
    return title, text


class SafeSourceFetcher:
    def __init__(
        self, policy: FetchPolicy | None = None, client: httpx.AsyncClient | None = None
    ) -> None:
        resolved_policy = policy or FetchPolicy()
        self._policy = resolved_policy
        self._client = client or httpx.AsyncClient(
            timeout=resolved_policy.timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": "TruthHunter/0.1 (+evidence research)"},
        )
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch(self, result: SearchResult) -> SourceDocument:
        current_url = str(result.url)
        for redirect_count in range(self._policy.redirect_limit + 1):
            await validate_public_url(current_url)
            try:
                async with self._client.stream("GET", current_url) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location or redirect_count >= self._policy.redirect_limit:
                            raise SourceFetchError("Source exceeded the redirect limit")
                        current_url = urljoin(current_url, location)
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if not content_type.startswith(ALLOWED_CONTENT_TYPES):
                        raise SourceFetchError("Source content type is not supported")
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > self._policy.max_bytes:
                            raise SourceFetchError("Source exceeded the maximum download size")
                        chunks.append(chunk)
            except httpx.HTTPError as exc:
                raise SourceFetchError("Source retrieval failed") from exc
            title, text = _extract_text(b"".join(chunks), content_type)
            if not text:
                raise SourceFetchError("Source did not contain extractable text")
            parsed = urlsplit(current_url)
            return SourceDocument(
                url=current_url,
                title=title or result.title,
                domain=parsed.hostname or "unknown",
                text=text[:100_000],
            )
        raise SourceFetchError("Source retrieval failed")

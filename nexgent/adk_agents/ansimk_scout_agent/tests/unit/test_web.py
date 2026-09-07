from __future__ import annotations

import httpx
import pytest

from app.models import SearchResult
from app.tools.web import (
    FetchLimits,
    SearchProvider,
    UnsafeUrlError,
    WebFetcher,
    canonicalize_public_url,
    normalize_search_results,
    select_search_results,
)


class StaticResolver:
    def __init__(self, *addresses: str) -> None:
        self.addresses = addresses

    async def resolve(self, hostname: str, port: int) -> list[str]:
        del hostname, port
        return list(self.addresses)


class StubSearchProvider(SearchProvider):
    async def search(self, query: str, limit: int) -> list[SearchResult]:
        del query, limit
        return []


def test_search_result_normalization_deduplicates_and_strips_tracking() -> None:
    raw = [
        {
            "title": "First",
            "href": "https://Example.com/story?utm_source=test&id=1#part",
            "body": "one",
        },
        {
            "title": "Duplicate",
            "url": "https://example.com/story?id=1",
            "snippet": "two",
        },
        {"title": "Unsafe", "href": "file:///etc/passwd", "body": "bad"},
        {"title": "Missing URL"},
    ]

    results = normalize_search_results(raw, limit=6)

    assert len(results) == 1
    assert str(results[0].url) == "https://example.com/story?id=1"
    assert results[0].title == "First"
    assert results[0].snippet == "one"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://localhost/admin",
        "http://10.0.0.8/private",
        "http://169.254.169.254/latest/meta-data",
        "ftp://example.com/file",
        "https://user:pass@example.com/",
    ],
)
async def test_url_safety_rejects_unsafe_targets(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        await canonicalize_public_url(url, resolver=StaticResolver("93.184.216.34"))


async def test_url_safety_rejects_hostname_resolving_private() -> None:
    with pytest.raises(UnsafeUrlError):
        await canonicalize_public_url(
            "https://internal.example/page",
            resolver=StaticResolver("192.168.1.10"),
        )


async def test_fetch_extracts_main_text_and_enforces_character_limit() -> None:
    html = b"""
    <html><head><title>Example story</title></head><body>
      <nav>Navigation noise</nav>
      <article><h1>Useful heading</h1><p>This is useful evidence repeated for testing.
      This is useful evidence repeated for testing.</p></article>
    </body></html>
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=html,
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = WebFetcher(
        client=client,
        resolver=StaticResolver("93.184.216.34"),
        limits=FetchLimits(max_response_bytes=4096, max_extracted_characters=45),
    )
    try:
        page = await fetcher.fetch("https://example.com/story")
    finally:
        await client.aclose()

    assert page.title == "Example story"
    assert page.content_is_untrusted is True
    assert len(page.text) <= 45
    assert page.truncated is True
    assert "Useful" in page.text


async def test_fetch_rejects_response_larger_than_bound() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"x" * 33,
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = WebFetcher(
        client=client,
        resolver=StaticResolver("93.184.216.34"),
        limits=FetchLimits(max_response_bytes=32),
    )
    try:
        with pytest.raises(ValueError, match="response byte limit"):
            await fetcher.fetch("https://example.com/large")
    finally:
        await client.aclose()


async def test_fetch_revalidates_redirect_destination() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/private"},
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = WebFetcher(
        client=client,
        resolver=StaticResolver("93.184.216.34"),
    )
    try:
        with pytest.raises(UnsafeUrlError):
            await fetcher.fetch("https://example.com/redirect")
    finally:
        await client.aclose()


def test_deterministic_selection_preserves_rank_deduplicates_and_bounds() -> None:
    results = [
        SearchResult(title="A", url="https://a.example/x?utm_source=test", snippet=""),
        SearchResult(title="A duplicate", url="https://a.example/x", snippet=""),
        SearchResult(title="B", url="https://b.example/y", snippet=""),
        SearchResult(title="C", url="https://c.example/z", snippet=""),
    ]

    selected = select_search_results(results, limit=2)

    assert [result.url for result in selected] == [
        "https://a.example/x",
        "https://b.example/y",
    ]

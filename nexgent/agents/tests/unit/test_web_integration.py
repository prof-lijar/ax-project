from collections.abc import Sequence

import httpx
import pytest
from ax_contracts import WebFetchInput, WebSearchInput
from ax_integrations import (
    SafeWebFetchClient,
    SearxngSearchClient,
    SearxngSettings,
    WebFetchSettings,
    WebRetrievalError,
    canonicalize_url,
    source_id_for_url,
)


class StaticResolver:
    def __init__(self, addresses: Sequence[str]) -> None:
        self.addresses = addresses
        self.calls: list[tuple[str, int]] = []

    async def resolve(self, hostname: str, port: int) -> Sequence[str]:
        self.calls.append((hostname, port))
        return self.addresses


@pytest.mark.asyncio
async def test_searxng_search_normalizes_filters_and_deduplicates() -> None:
    observed: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        observed.update(dict(request.url.params))
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "<b>LangGraph docs</b>",
                        "url": "https://docs.langchain.com/page?utm_source=test",
                        "content": "Official <em>documentation</em>",
                        "engines": ["google", "bing"],
                        "score": 9.5,
                    },
                    {
                        "title": "duplicate",
                        "url": "https://docs.langchain.com/page",
                        "content": "duplicate",
                    },
                    {
                        "title": "blocked by allowlist",
                        "url": "https://example.com/page",
                        "content": "other",
                    },
                ],
                "unresponsive_engines": [["duckduckgo", "timeout"]],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = SearxngSearchClient(
        SearxngSettings(base_url="http://searxng.internal", max_attempts=1),
        client=client,
    )
    try:
        output = await adapter.search(
            WebSearchInput(
                query="LangGraph",
                result_limit=5,
                language="en",
                time_range="month",
                allowed_domains=["langchain.com"],
            )
        )
    finally:
        await client.aclose()

    assert observed == {
        "q": "LangGraph",
        "format": "json",
        "categories": "general",
        "language": "en",
        "pageno": "1",
        "safesearch": "1",
        "time_range": "month",
    }
    assert len(output.results) == 1
    assert output.results[0].title == "LangGraph docs"
    assert output.results[0].url == "https://docs.langchain.com/page"
    assert output.results[0].snippet == "Official documentation"
    assert output.results[0].source_id == source_id_for_url(output.results[0].url)
    assert output.warnings == ["1 upstream search engine(s) were unavailable"]


@pytest.mark.asyncio
async def test_searxng_retries_transient_failures_and_safely_classifies_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, request=request, text="internal detail")
        return httpx.Response(200, json={"results": []})

    async def no_sleep(delay: float) -> None:
        assert delay == 0.25

    monkeypatch.setattr("ax_integrations.web.asyncio.sleep", no_sleep)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = SearxngSearchClient(
        SearxngSettings(base_url="http://searxng.internal", max_attempts=2),
        client=client,
    )
    try:
        output = await adapter.search(WebSearchInput(query="test"))
    finally:
        await client.aclose()

    assert attempts == 2
    assert output.results == []
    assert output.warnings == ["search returned no matching results"]


@pytest.mark.asyncio
async def test_searxng_rejects_malformed_json() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text="nope"))
    )
    adapter = SearxngSearchClient(
        SearxngSettings(base_url="http://searxng.internal", max_attempts=1),
        client=client,
    )
    try:
        with pytest.raises(WebRetrievalError) as exc_info:
            await adapter.search(WebSearchInput(query="test"))
    finally:
        await client.aclose()

    assert exc_info.value.error_code == "invalid_search_response"
    assert exc_info.value.retryable is False


@pytest.mark.asyncio
async def test_safe_fetch_pins_public_ip_extracts_html_and_truncates() -> None:
    observed: dict[str, object] = {}
    document = (
        "<html><head><title>Example Article</title></head><body><article><p>"
        + ("Useful public evidence. " * 100)
        + "</p></article></body></html>"
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["host"] = request.headers["host"]
        observed["sni"] = request.extensions.get("sni_hostname")
        observed["cookie"] = request.headers.get("cookie")
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=document.encode(),
        )

    resolver = StaticResolver(["93.184.216.34"])
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client.cookies.set("session", "must-not-cross", domain="93.184.216.34")
    adapter = SafeWebFetchClient(client=client, resolver=resolver)
    try:
        output = await adapter.fetch(
            WebFetchInput(
                url="https://Example.com/article?utm_source=test#section",
                max_characters=1_000,
            )
        )
    finally:
        await client.aclose()

    assert observed == {
        "url": "https://93.184.216.34/article",
        "host": "example.com",
        "sni": "example.com",
        "cookie": None,
    }
    assert resolver.calls == [("example.com", 443)]
    assert output.final_url == "https://example.com/article"
    assert output.title == "Example Article"
    assert output.content_type == "text/html"
    assert len(output.text) <= 1_000
    assert output.truncated is True
    assert output.content_is_untrusted is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "addresses",
    [
        ["127.0.0.1"],
        ["169.254.169.254"],
        ["10.0.0.1"],
        ["93.184.216.34", "192.168.1.10"],
    ],
)
async def test_safe_fetch_rejects_non_public_or_mixed_dns_answers(
    addresses: list[str],
) -> None:
    called = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, text="must not run")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = SafeWebFetchClient(client=client, resolver=StaticResolver(addresses))
    try:
        with pytest.raises(WebRetrievalError) as exc_info:
            await adapter.fetch(WebFetchInput(url="https://example.com"))
    finally:
        await client.aclose()

    assert exc_info.value.error_code == "unsafe_destination"
    assert called is False


@pytest.mark.asyncio
async def test_safe_fetch_revalidates_redirects() -> None:
    resolver = StaticResolver(["93.184.216.34"])

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = SafeWebFetchClient(client=client, resolver=resolver)
    try:
        with pytest.raises(WebRetrievalError) as exc_info:
            await adapter.fetch(WebFetchInput(url="https://example.com"))
    finally:
        await client.aclose()

    assert exc_info.value.error_code == "unsafe_destination"


@pytest.mark.asyncio
async def test_safe_fetch_bounds_redirects() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(302, headers={"location": "/again"})
        )
    )
    adapter = SafeWebFetchClient(
        WebFetchSettings(max_redirects=1),
        client=client,
        resolver=StaticResolver(["93.184.216.34"]),
    )
    try:
        with pytest.raises(WebRetrievalError) as exc_info:
            await adapter.fetch(WebFetchInput(url="https://example.com"))
    finally:
        await client.aclose()

    assert exc_info.value.error_code == "too_many_redirects"


@pytest.mark.asyncio
async def test_safe_fetch_classifies_transport_timeout_as_retryable() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("internal address must not escape", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = SafeWebFetchClient(
        client=client,
        resolver=StaticResolver(["93.184.216.34"]),
    )
    try:
        with pytest.raises(WebRetrievalError) as exc_info:
            await adapter.fetch(WebFetchInput(url="https://example.com"))
    finally:
        await client.aclose()

    assert exc_info.value.error_code == "fetch_unavailable"
    assert exc_info.value.retryable is True
    assert "internal address" not in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "content", "error_code"),
    [
        ({"content-type": "application/pdf"}, b"pdf", "unsupported_content_type"),
        (
            {"content-type": "text/plain", "content-length": "200"},
            b"small",
            "response_too_large",
        ),
        (
            {"content-type": "text/plain"},
            b"x" * 101,
            "response_too_large",
        ),
    ],
)
async def test_safe_fetch_bounds_type_and_size(
    headers: dict[str, str],
    content: bytes,
    error_code: str,
) -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers=headers, content=content)
        )
    )
    adapter = SafeWebFetchClient(
        WebFetchSettings(max_download_bytes=100),
        client=client,
        resolver=StaticResolver(["93.184.216.34"]),
    )
    try:
        with pytest.raises(WebRetrievalError) as exc_info:
            await adapter.fetch(WebFetchInput(url="https://example.com"))
    finally:
        await client.aclose()

    assert exc_info.value.error_code == error_code


def test_url_canonicalization_is_stable_and_removes_tracking() -> None:
    first = canonicalize_url(
        "HTTPS://Example.COM:443/path?x=1&utm_campaign=test&fbclid=abc#fragment"
    )
    second = canonicalize_url("https://example.com/path?x=1")
    assert first == second == "https://example.com/path?x=1"
    assert source_id_for_url(first) == source_id_for_url(second)

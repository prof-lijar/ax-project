from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx
import trafilatura
from ddgs import DDGS

from app.models import FetchedPage, SearchResult

TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref_src",
}
ALLOWED_CONTENT_TYPES = {"text/html", "application/xhtml+xml", "text/plain"}


class UnsafeUrlError(ValueError):
    """Raised when a URL is outside the public HTTP(S) boundary."""


class SearchProvider(Protocol):
    async def search(self, query: str, limit: int) -> list[SearchResult]: ...


class PageFetcher(Protocol):
    async def fetch(self, url: str) -> FetchedPage: ...

    async def aclose(self) -> None: ...


class HostResolver(Protocol):
    async def resolve(self, hostname: str, port: int) -> list[str]: ...


class AsyncHostResolver:
    async def resolve(self, hostname: str, port: int) -> list[str]:
        # Resolve before the separately time-bounded HTTP request. Keeping this
        # inline also works in minimal environments without executor wake-up pipes.
        records = socket.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
        return sorted({record[4][0] for record in records})


@dataclass(frozen=True, slots=True)
class FetchLimits:
    timeout_seconds: float = 12.0
    max_redirects: int = 3
    max_response_bytes: int = 1_048_576
    max_extracted_characters: int = 12_000


def _canonicalize_url_syntax(url: str) -> str:
    try:
        parsed = urlsplit(url.strip())
        port = parsed.port
    except ValueError as exc:
        raise UnsafeUrlError("URL is malformed") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise UnsafeUrlError("only HTTP(S) URLs are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeUrlError("credential-bearing URLs are not allowed")
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if not hostname:
        raise UnsafeUrlError("URL must contain a hostname")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise UnsafeUrlError("local URLs are not allowed")

    default_port = (scheme == "http" and port in {None, 80}) or (
        scheme == "https" and port in {None, 443}
    )
    host_for_netloc = f"[{hostname}]" if ":" in hostname else hostname
    netloc = host_for_netloc if default_port else f"{host_for_netloc}:{port}"
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMETERS
        ],
        doseq=True,
    )
    return urlunsplit((scheme, netloc, parsed.path or "/", query, ""))


async def canonicalize_public_url(
    url: str,
    *,
    resolver: HostResolver | None = None,
) -> str:
    canonical = _canonicalize_url_syntax(url)
    parsed = urlsplit(canonical)
    hostname = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addresses = [str(ipaddress.ip_address(hostname))]
    except ValueError:
        addresses = await (resolver or AsyncHostResolver()).resolve(hostname, port)
    if not addresses:
        raise UnsafeUrlError("hostname did not resolve")
    for address in addresses:
        try:
            parsed_address = ipaddress.ip_address(address.split("%", 1)[0])
        except ValueError as exc:
            raise UnsafeUrlError("hostname returned an invalid address") from exc
        if not parsed_address.is_global:
            raise UnsafeUrlError("private or local network targets are not allowed")
    return canonical


def normalize_search_results(
    raw_results: Iterable[Mapping[str, Any]],
    *,
    limit: int,
) -> list[SearchResult]:
    results: list[SearchResult] = []
    seen: set[str] = set()
    for raw in raw_results:
        raw_url = raw.get("href") or raw.get("url")
        if not isinstance(raw_url, str):
            continue
        try:
            url = _canonicalize_url_syntax(raw_url)
        except UnsafeUrlError:
            continue
        if url in seen:
            continue
        title = str(raw.get("title") or url).strip()
        snippet = str(raw.get("body") or raw.get("snippet") or "").strip()
        seen.add(url)
        results.append(SearchResult(title=title, url=url, snippet=snippet))
        if len(results) >= limit:
            break
    return results


def select_search_results(
    results: Iterable[SearchResult],
    *,
    limit: int,
) -> list[SearchResult]:
    """Select the first unique eligible URLs while preserving merged search rank."""
    selected: list[SearchResult] = []
    seen: set[str] = set()
    for result in results:
        try:
            url = _canonicalize_url_syntax(result.url)
        except UnsafeUrlError:
            continue
        if url in seen:
            continue
        seen.add(url)
        selected.append(result.model_copy(update={"url": url}))
        if len(selected) >= limit:
            break
    return selected


class DdgsSearchProvider:
    """Small replaceable adapter around the DDGS search package."""

    def __init__(self, ddgs_factory: Callable[[], DDGS] = DDGS) -> None:
        self._ddgs_factory = ddgs_factory

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        raw_results: Sequence[Mapping[str, Any]] = list(
            self._ddgs_factory().text(query, max_results=limit)
        )
        return normalize_search_results(raw_results, limit=limit)


class _DocumentTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._in_title = False
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if not value or self._ignored_depth:
            return
        if self._in_title:
            self.title_parts.append(value)
        self.text_parts.append(value)

    @property
    def title(self) -> str | None:
        value = " ".join(self.title_parts).strip()
        return value or None

    @property
    def text(self) -> str:
        return "\n".join(self.text_parts)


class WebFetcher:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        resolver: HostResolver | None = None,
        limits: FetchLimits | None = None,
    ) -> None:
        self._limits = limits or FetchLimits()
        self._resolver = resolver or AsyncHostResolver()
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(self._limits.timeout_seconds),
            follow_redirects=False,
            trust_env=False,
            headers={
                "User-Agent": "ansimk-scout-agent/0.1 (+bounded research POC)",
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
            },
            limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
        )

    async def fetch(self, url: str) -> FetchedPage:
        current_url = await canonicalize_public_url(url, resolver=self._resolver)
        for redirect_count in range(self._limits.max_redirects + 1):
            async with self._client.stream("GET", current_url) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("redirect response is missing a destination")
                    if redirect_count >= self._limits.max_redirects:
                        raise ValueError("redirect limit exceeded")
                    current_url = await canonicalize_public_url(
                        urljoin(current_url, location),
                        resolver=self._resolver,
                    )
                    continue

                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if content_type not in ALLOWED_CONTENT_TYPES:
                    raise ValueError("unsupported webpage content type")
                declared_length = response.headers.get("content-length")
                if declared_length:
                    try:
                        if int(declared_length) > self._limits.max_response_bytes:
                            raise ValueError("response byte limit exceeded")
                    except ValueError as exc:
                        if str(exc) == "response byte limit exceeded":
                            raise

                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > self._limits.max_response_bytes:
                        raise ValueError("response byte limit exceeded")
                encoding = response.encoding or "utf-8"
                decoded = bytes(body).decode(encoding, errors="replace")

            if content_type == "text/plain":
                title = None
                extracted = decoded
            else:
                parser = _DocumentTextParser()
                parser.feed(decoded)
                title = parser.title
                extracted = trafilatura.extract(
                    decoded,
                    url=current_url,
                    include_comments=False,
                    include_tables=False,
                    favor_precision=True,
                )
                if not extracted:
                    extracted = parser.text
            extracted = (extracted or "").strip()
            if not extracted:
                raise ValueError("no useful text could be extracted from webpage")
            truncated = len(extracted) > self._limits.max_extracted_characters
            text = extracted[: self._limits.max_extracted_characters]
            return FetchedPage(
                url=current_url,
                title=title,
                text=text,
                content_type=content_type,
                truncated=truncated,
            )
        raise ValueError("redirect limit exceeded")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

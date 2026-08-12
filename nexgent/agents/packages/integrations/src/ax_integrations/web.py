"""Provider-neutral public-web search and safe page retrieval adapters."""

from __future__ import annotations

import asyncio
import hashlib
import html
import ipaddress
import json
import os
import re
import socket
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from html.parser import HTMLParser
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx
import trafilatura
from ax_contracts import (
    WebFetchInput,
    WebFetchOutput,
    WebSearchInput,
    WebSearchOutput,
    WebSearchResult,
)

_TRACKING_QUERY_KEYS = {
    "dclid",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "msclkid",
}
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_FETCH_CONTENT_TYPES = {"text/html", "application/xhtml+xml", "text/plain"}
_DEFAULT_USER_AGENT = "AX-WebResearch/0.1 (+private agent runtime)"
_DEFAULT_SEARXNG_BASE_URL = "http://searxng:8080"


class WebRetrievalError(RuntimeError):
    """Safe retrieval failure with an explicit retry decision."""

    def __init__(
        self,
        error_code: str,
        safe_message: str,
        *,
        retryable: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(safe_message)
        self.error_code = error_code
        self.safe_message = safe_message
        self.retryable = retryable
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class SearxngSettings:
    base_url: str = _DEFAULT_SEARXNG_BASE_URL
    timeout_seconds: float = 12.0
    max_attempts: int = 2

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("SearXNG base URL must be an absolute HTTP(S) URL")
        if self.timeout_seconds <= 0:
            raise ValueError("SearXNG timeout must be positive")
        if self.max_attempts < 1:
            raise ValueError("SearXNG max attempts must be at least 1")

    @property
    def search_url(self) -> str:
        return self.base_url.rstrip("/") + "/search"

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> SearxngSettings:
        values = os.environ if environ is None else environ
        return cls(
            base_url=values.get("SEARXNG_BASE_URL", _DEFAULT_SEARXNG_BASE_URL)
        )


@dataclass(frozen=True, slots=True)
class WebFetchSettings:
    timeout_seconds: float = 15.0
    max_redirects: int = 3
    max_download_bytes: int = 2 * 1024 * 1024
    max_extracted_characters: int = 40_000

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("fetch timeout must be positive")
        if self.max_redirects < 0:
            raise ValueError("maximum redirects must not be negative")
        if self.max_download_bytes < 1:
            raise ValueError("maximum download size must be positive")
        if self.max_extracted_characters < 1:
            raise ValueError("maximum extracted size must be positive")


class HostResolver(Protocol):
    async def resolve(self, hostname: str, port: int) -> Sequence[str]: ...


class AsyncHostResolver:
    async def resolve(self, hostname: str, port: int) -> Sequence[str]:
        loop = asyncio.get_running_loop()
        records = await loop.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
        return list(dict.fromkeys(record[4][0] for record in records))


class SearxngSearchClient:
    """Pooled asynchronous adapter for a private SearXNG JSON API."""

    def __init__(
        self,
        settings: SearxngSettings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.timeout_seconds),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
            trust_env=False,
            headers={"User-Agent": _DEFAULT_USER_AGENT},
        )

    async def search(self, input: WebSearchInput) -> WebSearchOutput:
        params: dict[str, str | int] = {
            "q": input.query,
            "format": "json",
            "categories": "general",
            "language": input.language,
            "pageno": 1,
            "safesearch": 1,
        }
        if input.time_range:
            params["time_range"] = input.time_range

        payload = await self._request_json(params)
        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            raise WebRetrievalError(
                "invalid_search_response",
                "search service returned an invalid response",
                retryable=False,
            )

        results: list[WebSearchResult] = []
        seen_urls: set[str] = set()
        for raw_result in raw_results:
            result = _normalize_search_result(raw_result)
            if result is None or result.url in seen_urls:
                continue
            if not _domain_is_allowed(
                result.domain,
                input.allowed_domains,
                input.blocked_domains,
            ):
                continue
            seen_urls.add(result.url)
            results.append(result)
            if len(results) >= input.result_limit:
                break

        warnings: list[str] = []
        unavailable = payload.get("unresponsive_engines")
        if isinstance(unavailable, list) and unavailable:
            warnings.append(
                f"{len(unavailable)} upstream search engine(s) were unavailable"
            )
        if not results:
            warnings.append("search returned no matching results")
        return WebSearchOutput(
            original_query=input.query,
            results=results,
            warnings=warnings,
        )

    async def _request_json(self, params: dict[str, str | int]) -> dict[str, Any]:
        for attempt in range(1, self.settings.max_attempts + 1):
            try:
                response = await self._client.get(self.settings.search_url, params=params)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise json.JSONDecodeError("expected object", "", 0)
                return payload
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                retryable = status_code == 429 or 500 <= status_code < 600
                error = WebRetrievalError(
                    "search_rate_limited" if status_code == 429 else "search_failed",
                    f"search service failed with HTTP {status_code}",
                    retryable=retryable,
                    status_code=status_code,
                )
            except (httpx.TransportError, TimeoutError) as exc:
                error = WebRetrievalError(
                    "search_unavailable",
                    f"search service is unavailable ({type(exc).__name__})",
                    retryable=True,
                )
            except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
                raise WebRetrievalError(
                    "invalid_search_response",
                    "search service returned an invalid response",
                    retryable=False,
                ) from exc

            if not error.retryable or attempt >= self.settings.max_attempts:
                raise error
            await asyncio.sleep(0.25 * (2 ** (attempt - 1)))
        raise AssertionError("unreachable")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


@dataclass(frozen=True, slots=True)
class _ResolvedTarget:
    original_url: str
    connect_url: str
    host_header: str
    sni_hostname: str | None


class SafeWebFetchClient:
    """Fetch public pages while pinning validated DNS results against SSRF."""

    def __init__(
        self,
        settings: WebFetchSettings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        resolver: HostResolver | None = None,
    ) -> None:
        self.settings = settings or WebFetchSettings()
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.settings.timeout_seconds),
            limits=httpx.Limits(max_connections=30, max_keepalive_connections=0),
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": _DEFAULT_USER_AGENT},
        )
        self._resolver = resolver or AsyncHostResolver()

    async def fetch(self, input: WebFetchInput) -> WebFetchOutput:
        current_url = canonicalize_url(input.url)
        response_body: bytes | None = None
        content_type = ""

        for redirect_count in range(self.settings.max_redirects + 1):
            target = await self._resolve_target(current_url)
            headers = {
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
                "Host": target.host_header,
            }
            extensions: dict[str, object] = {}
            if target.sni_hostname:
                extensions["sni_hostname"] = target.sni_hostname
            try:
                request = self._client.build_request(
                    "GET",
                    target.connect_url,
                    headers=headers,
                    extensions=extensions,
                )
                request.headers.pop("cookie", None)
                response = await self._client.send(
                    request,
                    stream=True,
                    follow_redirects=False,
                )
                try:
                    if response.status_code in _REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        if not location:
                            raise WebRetrievalError(
                                "invalid_redirect",
                                "web page returned an invalid redirect",
                                retryable=False,
                            )
                        if redirect_count >= self.settings.max_redirects:
                            raise WebRetrievalError(
                                "too_many_redirects",
                                "web page exceeded the redirect limit",
                                retryable=False,
                            )
                        current_url = canonicalize_url(urljoin(current_url, location))
                        continue

                    if response.status_code >= 400:
                        retryable = response.status_code == 429 or (
                            500 <= response.status_code < 600
                        )
                        raise WebRetrievalError(
                            "fetch_rate_limited"
                            if response.status_code == 429
                            else "fetch_failed",
                            f"web page failed with HTTP {response.status_code}",
                            retryable=retryable,
                            status_code=response.status_code,
                        )

                    content_type = _normalized_content_type(
                        response.headers.get("content-type")
                    )
                    if content_type not in _FETCH_CONTENT_TYPES:
                        raise WebRetrievalError(
                            "unsupported_content_type",
                            "web page content type is not supported",
                            retryable=False,
                        )
                    _validate_content_length(
                        response.headers.get("content-length"),
                        self.settings.max_download_bytes,
                    )
                    chunks: list[bytes] = []
                    downloaded = 0
                    async for chunk in response.aiter_bytes():
                        downloaded += len(chunk)
                        if downloaded > self.settings.max_download_bytes:
                            raise WebRetrievalError(
                                "response_too_large",
                                "web page exceeded the download limit",
                                retryable=False,
                            )
                        chunks.append(chunk)
                    response_body = b"".join(chunks)
                    charset = response.charset_encoding or "utf-8"
                finally:
                    await response.aclose()
                break
            except WebRetrievalError:
                raise
            except (httpx.TransportError, TimeoutError) as exc:
                raise WebRetrievalError(
                    "fetch_unavailable",
                    f"web page is unavailable ({type(exc).__name__})",
                    retryable=True,
                ) from exc

        if response_body is None:
            raise AssertionError("redirect loop exited without a response")
        try:
            decoded = response_body.decode(charset, errors="replace")
        except LookupError:
            decoded = response_body.decode("utf-8", errors="replace")

        if content_type == "text/plain":
            extracted = decoded.strip()
            title = None
        else:
            extracted, title = _extract_html(decoded, current_url)
        if not extracted:
            raise WebRetrievalError(
                "content_extraction_failed",
                "web page did not contain readable text",
                retryable=False,
            )

        hard_limit = min(
            input.max_characters,
            self.settings.max_extracted_characters,
        )
        truncated = len(extracted) > hard_limit
        text = extracted[:hard_limit].rstrip()
        final_url = canonicalize_url(current_url)
        return WebFetchOutput(
            source_id=source_id_for_url(final_url),
            final_url=final_url,
            title=title,
            text=text,
            content_type=content_type,
            retrieved_at=datetime.now(UTC),
            truncated=truncated,
            content_is_untrusted=True,
        )

    async def _resolve_target(self, url: str) -> _ResolvedTarget:
        try:
            parsed = urlsplit(url)
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as exc:
            raise WebRetrievalError(
                "invalid_url",
                "web page URL is invalid",
                retryable=False,
            ) from exc
        hostname = parsed.hostname
        if parsed.scheme not in {"http", "https"} or not hostname:
            raise WebRetrievalError(
                "invalid_url",
                "web page URL must use HTTP(S)",
                retryable=False,
            )
        if parsed.username is not None or parsed.password is not None:
            raise WebRetrievalError(
                "invalid_url",
                "web page URL must not contain credentials",
                retryable=False,
            )
        ascii_hostname = _ascii_hostname(hostname)

        try:
            literal_ip = ipaddress.ip_address(ascii_hostname)
            addresses = [str(literal_ip)]
        except ValueError:
            try:
                addresses = list(await self._resolver.resolve(ascii_hostname, port))
            except (OSError, UnicodeError) as exc:
                raise WebRetrievalError(
                    "dns_failed",
                    "web page hostname could not be resolved",
                    retryable=True,
                ) from exc
        if not addresses:
            raise WebRetrievalError(
                "dns_failed",
                "web page hostname could not be resolved",
                retryable=True,
            )

        parsed_addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        for address in addresses:
            try:
                parsed_address = ipaddress.ip_address(address)
            except ValueError as exc:
                raise WebRetrievalError(
                    "unsafe_destination",
                    "web page resolved to an invalid destination",
                    retryable=False,
                ) from exc
            if not parsed_address.is_global:
                raise WebRetrievalError(
                    "unsafe_destination",
                    "web page destination is not public",
                    retryable=False,
                )
            parsed_addresses.append(parsed_address)

        selected = min(
            parsed_addresses,
            key=lambda address: (address.version, int(address)),
        )
        ip_host = f"[{selected}]" if selected.version == 6 else str(selected)
        explicit_port = parsed.port is not None
        connect_netloc = f"{ip_host}:{port}" if explicit_port else ip_host
        connect_url = urlunsplit(
            (
                parsed.scheme,
                connect_netloc,
                parsed.path or "/",
                parsed.query,
                "",
            )
        )
        display_host = f"[{ascii_hostname}]" if ":" in ascii_hostname else ascii_hostname
        host_header = f"{display_host}:{port}" if explicit_port else display_host
        return _ResolvedTarget(
            original_url=url,
            connect_url=connect_url,
            host_header=host_header,
            sni_hostname=ascii_hostname if parsed.scheme == "https" else None,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def canonicalize_url(url: str) -> str:
    try:
        parsed = urlsplit(url.strip())
        port = parsed.port
    except ValueError as exc:
        raise WebRetrievalError(
            "invalid_url",
            "web page URL is invalid",
            retryable=False,
        ) from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise WebRetrievalError(
            "invalid_url",
            "web page URL must use HTTP(S)",
            retryable=False,
        )
    if parsed.username is not None or parsed.password is not None:
        raise WebRetrievalError(
            "invalid_url",
            "web page URL must not contain credentials",
            retryable=False,
        )
    hostname = _ascii_hostname(parsed.hostname)
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    default_port = (parsed.scheme.lower() == "http" and port == 80) or (
        parsed.scheme.lower() == "https" and port == 443
    )
    netloc = display_host if port is None or default_port else f"{display_host}:{port}"
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
            and key.lower() not in _TRACKING_QUERY_KEYS
        ],
        doseq=True,
    )
    return urlunsplit(
        (parsed.scheme.lower(), netloc, parsed.path or "/", query, "")
    )


def source_id_for_url(url: str) -> str:
    canonical = canonicalize_url(url)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"src_{digest}"


def _normalize_search_result(raw: object) -> WebSearchResult | None:
    if not isinstance(raw, dict):
        return None
    raw_url = raw.get("url")
    if not isinstance(raw_url, str):
        return None
    try:
        url = canonicalize_url(raw_url)
    except WebRetrievalError:
        return None
    domain = urlsplit(url).hostname
    if not domain:
        return None
    title = _plain_text(raw.get("title")) or domain
    snippet = _plain_text(raw.get("content"))
    raw_engines = raw.get("engines")
    if isinstance(raw_engines, list):
        engines = [str(engine)[:128] for engine in raw_engines[:32] if engine]
    elif raw.get("engine"):
        engines = [str(raw["engine"])[:128]]
    else:
        engines = []
    published_at = _parse_datetime(raw.get("publishedDate") or raw.get("pubdate"))
    raw_score = raw.get("score")
    score = float(raw_score) if isinstance(raw_score, (int, float)) else None
    return WebSearchResult(
        source_id=source_id_for_url(url),
        title=title[:2_000],
        url=url,
        domain=_ascii_hostname(domain),
        snippet=snippet[:8_000],
        engines=list(dict.fromkeys(engines)),
        published_at=published_at,
        score=score,
    )


def _domain_is_allowed(
    domain: str,
    allowed_domains: list[str] | None,
    blocked_domains: list[str] | None,
) -> bool:
    def matches(candidate: str) -> bool:
        return domain == candidate or domain.endswith("." + candidate)

    if allowed_domains is not None:
        return any(matches(candidate) for candidate in allowed_domains)
    if blocked_domains is not None:
        return not any(matches(candidate) for candidate in blocked_domains)
    return True


def _ascii_hostname(hostname: str) -> str:
    try:
        return hostname.rstrip(".").lower().encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise WebRetrievalError(
            "invalid_url",
            "web page hostname is invalid",
            retryable=False,
        ) from exc


def _plain_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    without_markup = re.sub(r"<[^>]*>", " ", html.unescape(value))
    return " ".join(without_markup.split())


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _normalized_content_type(header: str | None) -> str:
    if not header:
        return ""
    return header.split(";", maxsplit=1)[0].strip().lower()


def _validate_content_length(header: str | None, maximum: int) -> None:
    if not header:
        return
    try:
        length = int(header)
    except ValueError as exc:
        raise WebRetrievalError(
            "invalid_fetch_response",
            "web page returned an invalid content length",
            retryable=False,
        ) from exc
    if length < 0:
        raise WebRetrievalError(
            "invalid_fetch_response",
            "web page returned an invalid content length",
            retryable=False,
        )
    if length > maximum:
        raise WebRetrievalError(
            "response_too_large",
            "web page exceeded the download limit",
            retryable=False,
        )


class _TitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._inside_title = False
        self.parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag.lower() == "title":
            self._inside_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._inside_title = False

    def handle_data(self, data: str) -> None:
        if self._inside_title:
            self.parts.append(data)


def _extract_html(document: str, url: str) -> tuple[str, str | None]:
    extracted = trafilatura.extract(
        document,
        url=url,
        output_format="txt",
        include_comments=False,
        include_tables=True,
        favor_precision=True,
    )
    parser = _TitleParser()
    parser.feed(document)
    normalized_title = " ".join("".join(parser.parts).split())
    title = normalized_title[:2_000] or None
    normalized = (extracted or "").replace("\x00", "").strip()
    return normalized, title


@lru_cache(maxsize=1)
def get_default_web_search_client() -> SearxngSearchClient:
    return SearxngSearchClient(SearxngSettings.from_env())


@lru_cache(maxsize=1)
def get_default_web_fetch_client() -> SafeWebFetchClient:
    return SafeWebFetchClient()

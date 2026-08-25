"""Read-only client for the dedicated RAG search service."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

DEFAULT_RAG_TOP_K = 5
MAX_RAG_TOP_K = 20


class RagSearchResult(BaseModel):
    """One exact-cosine result returned by the existing RAG service."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    similarity: float
    context: str = Field(min_length=1)
    document_id: int | None
    source_type: Literal["file", "text"] | None
    source_name: str | None
    chunk_index: int | None
    source_start_character: int | None
    source_end_character: int | None
    token_count: int | None


class RagSearchTiming(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query_embedding: float = Field(ge=0)
    database_search: float = Field(ge=0)
    total: float = Field(ge=0)


class RagSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    results: list[RagSearchResult]
    timing_ms: RagSearchTiming


class RagSearchConfigurationError(ValueError):
    """Raised when the private RAG endpoint is not configured safely."""


class RagSearchError(RuntimeError):
    """Sanitized failure from the read-only RAG search boundary."""


class RagSearchSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: str
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)

    @property
    def search_url(self) -> str:
        return self.base_url.rstrip("/") + "/rag/v1/search"

    @classmethod
    def from_env(cls) -> RagSearchSettings:
        base_url = os.environ.get("RAG_SERVER_BASE_URL", "").strip()
        if not base_url:
            raise RagSearchConfigurationError("RAG_SERVER_BASE_URL is required")
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise RagSearchConfigurationError(
                "RAG_SERVER_BASE_URL must be a credential-free HTTP(S) URL"
            )
        timeout_text = os.environ.get("RAG_SEARCH_TIMEOUT_SECONDS", "30").strip()
        try:
            timeout_seconds = float(timeout_text)
        except ValueError as exc:
            raise RagSearchConfigurationError(
                "RAG_SEARCH_TIMEOUT_SECONDS must be numeric"
            ) from exc
        try:
            return cls(base_url=base_url, timeout_seconds=timeout_seconds)
        except ValidationError as exc:
            raise RagSearchConfigurationError("RAG search settings are invalid") from exc


class RagSearchClient:
    """Pooled HTTP client exposing only the existing read-only search operation."""

    def __init__(
        self,
        settings: RagSearchSettings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.timeout_seconds),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
        )

    async def search(
        self,
        query: str,
        *,
        top_k: int = DEFAULT_RAG_TOP_K,
    ) -> RagSearchResponse:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        if (
            not isinstance(top_k, int)
            or isinstance(top_k, bool)
            or not 1 <= top_k <= MAX_RAG_TOP_K
        ):
            raise ValueError(f"top_k must be between 1 and {MAX_RAG_TOP_K}")

        try:
            response = await self._client.get(
                self.settings.search_url,
                params={"query": query, "top_k": str(top_k)},
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return RagSearchResponse.model_validate(response.json())
        except (httpx.HTTPError, ValidationError, ValueError) as exc:
            raise RagSearchError("RAG retrieval is temporarily unavailable.") from exc

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


@lru_cache(maxsize=1)
def get_default_rag_search_client() -> RagSearchClient:
    """Return one process-wide read-only RAG client and connection pool."""

    return RagSearchClient(RagSearchSettings.from_env())

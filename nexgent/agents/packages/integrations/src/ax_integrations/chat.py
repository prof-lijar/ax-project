"""Async adapter for OpenAI-compatible chat-completions endpoints."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal, Protocol, TypedDict
from urllib.parse import urlsplit

import httpx

COMPLETIONS_PATH = "/chat/completions"


class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatModel(Protocol):
    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> str: ...

    def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]: ...


class ModelConfigurationError(ValueError):
    """Raised when required model configuration is absent or invalid."""


class ModelRequestError(RuntimeError):
    """Safe model-provider failure with an explicit retry classification."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class OpenAICompatibleSettings:
    base_url: str
    model: str
    api_key: str = field(repr=False)
    timeout_seconds: float = 120.0
    max_attempts: int = 3

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ModelConfigurationError("model base URL must be an HTTP(S) URL")
        if not self.model.strip():
            raise ModelConfigurationError("model name must not be empty")
        if not self.api_key:
            raise ModelConfigurationError("OPENAI_API_KEY must not be empty")
        if self.timeout_seconds <= 0:
            raise ModelConfigurationError("model timeout must be positive")
        if self.max_attempts < 1:
            raise ModelConfigurationError("model max attempts must be at least 1")

    @property
    def completions_url(self) -> str:
        normalized = self.base_url.rstrip("/")
        if normalized.endswith(COMPLETIONS_PATH):
            return normalized
        if normalized.endswith("/v1"):
            return normalized + COMPLETIONS_PATH
        return normalized + "/v1" + COMPLETIONS_PATH

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> OpenAICompatibleSettings:
        values = os.environ if environ is None else environ
        base_url = values.get("OPENAI_BASE_URL") or values.get("URL")
        model = values.get("OPENAI_MODEL") or values.get("MODEL")
        api_key = values.get("OPENAI_API_KEY")

        missing = [
            name
            for name, value in (
                ("URL (or OPENAI_BASE_URL)", base_url),
                ("MODEL (or OPENAI_MODEL)", model),
                ("OPENAI_API_KEY", api_key),
            )
            if not value
        ]
        if missing:
            raise ModelConfigurationError(
                "missing model configuration: " + ", ".join(missing)
            )

        return cls(base_url=base_url, model=model, api_key=api_key)


class OpenAICompatibleChatModel:
    """Pooled async client for vLLM and other OpenAI-compatible servers."""

    def __init__(
        self,
        settings: OpenAICompatibleSettings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.timeout_seconds),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> str:
        chunks = [
            chunk
            async for chunk in self.stream(
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        ]
        response = "".join(chunks)
        if not response:
            raise ModelRequestError(
                "model returned an empty response",
                retryable=False,
            )
        return response

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        payload = self._build_payload(messages, max_tokens, temperature)

        for attempt in range(1, self.settings.max_attempts + 1):
            emitted_content = False
            try:
                async with self._client.stream(
                    "POST",
                    self.settings.completions_url,
                    headers={
                        "Authorization": f"Bearer {self.settings.api_key}",
                        "Accept": "text/event-stream",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for chunk in self._iter_sse_content(response):
                        emitted_content = True
                        yield chunk
                return
            except httpx.HTTPStatusError as exc:
                retryable = exc.response.status_code == 429 or (
                    500 <= exc.response.status_code < 600
                )
                error = ModelRequestError(
                    f"model request failed with HTTP {exc.response.status_code}",
                    retryable=retryable,
                    status_code=exc.response.status_code,
                )
            except httpx.TransportError as exc:
                error = ModelRequestError(
                    f"model request failed: {type(exc).__name__}",
                    retryable=True,
                )
            except ModelRequestError as exc:
                error = exc

            can_retry = (
                error.retryable
                and not emitted_content
                and attempt < self.settings.max_attempts
            )
            if not can_retry:
                raise error
            await asyncio.sleep(0.25 * (2 ** (attempt - 1)))

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _build_payload(
        self,
        messages: Sequence[ChatMessage],
        max_tokens: int,
        temperature: float,
    ) -> dict[str, object]:
        if not messages:
            raise ValueError("messages must not be empty")
        if max_tokens < 1:
            raise ValueError("max_tokens must be at least 1")
        if not 0 <= temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")

        normalized_messages: list[ChatMessage] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content")
            if role not in {"system", "user", "assistant"}:
                raise ValueError(f"unsupported message role: {role!r}")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("message content must be a non-empty string")
            normalized_messages.append({"role": role, "content": content})

        return {
            "model": self.settings.model,
            "messages": normalized_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }

    async def _iter_sse_content(
        self,
        response: httpx.Response,
    ) -> AsyncIterator[str]:
        async for line in response.aiter_lines():
            if not line.startswith("data:"):
                continue
            data = line.removeprefix("data:").strip()
            if data == "[DONE]":
                return
            if not data:
                continue
            try:
                event = json.loads(data)
                choices = event["choices"]
                content = choices[0].get("delta", {}).get("content")
            except (IndexError, KeyError, TypeError, json.JSONDecodeError) as exc:
                raise ModelRequestError(
                    "model returned an invalid streaming event",
                    retryable=False,
                ) from exc
            if content is not None:
                if not isinstance(content, str):
                    raise ModelRequestError(
                        "model returned non-text content",
                        retryable=False,
                    )
                yield content


@lru_cache(maxsize=1)
def get_default_chat_model() -> OpenAICompatibleChatModel:
    """Return one process-wide model client and connection pool."""

    return OpenAICompatibleChatModel(OpenAICompatibleSettings.from_env())

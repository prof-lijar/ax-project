"""Async adapter for OpenAI-compatible chat-completions endpoints."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal, Protocol, TypedDict
from urllib.parse import urlsplit

import httpx

COMPLETIONS_PATH = "/chat/completions"


class ChatTextContentPart(TypedDict):
    type: Literal["text"]
    text: str


class ChatImageUrl(TypedDict):
    url: str


class ChatImageContentPart(TypedDict):
    type: Literal["image_url"]
    image_url: ChatImageUrl


ChatContentPart = ChatTextContentPart | ChatImageContentPart


class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str | list[ChatContentPart]


class ChatModel(Protocol):
    @property
    def supports_vision(self) -> bool: ...

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
class StructuredChatCompletion:
    """Validated provider-neutral metadata for one non-streaming completion."""

    text: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    finish_reason: str | None
    latency_ms: int


@dataclass(frozen=True, slots=True)
class OpenAICompatibleSettings:
    base_url: str
    model: str
    api_key: str = field(repr=False)
    timeout_seconds: float = 120.0
    max_attempts: int = 3
    supports_vision: bool = False

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
        if not isinstance(self.supports_vision, bool):
            raise ModelConfigurationError("supports_vision must be a boolean")

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
        supports_vision_value = values.get("OPENAI_SUPPORTS_VISION", "false")

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

        normalized_supports_vision = supports_vision_value.strip().lower()
        if normalized_supports_vision not in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
            raise ModelConfigurationError(
                "OPENAI_SUPPORTS_VISION must be a boolean value"
            )

        return cls(
            base_url=base_url,
            model=model,
            api_key=api_key,
            supports_vision=normalized_supports_vision in {"1", "true", "yes", "on"},
        )


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

    @property
    def supports_vision(self) -> bool:
        return self.settings.supports_vision

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

    async def complete_structured(
        self,
        messages: Sequence[ChatMessage],
        *,
        response_schema: Mapping[str, object],
        schema_name: str,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> StructuredChatCompletion:
        """Request JSON-schema constrained output without SSE overhead."""

        if not schema_name or len(schema_name) > 64:
            raise ValueError("schema_name must contain 1 to 64 characters")
        payload = self._build_payload(messages, max_tokens, temperature)
        payload["stream"] = False
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": dict(response_schema),
            },
        }
        started = time.perf_counter()
        for attempt in range(1, self.settings.max_attempts + 1):
            try:
                response = await self._client.post(
                    self.settings.completions_url,
                    headers={
                        "Authorization": f"Bearer {self.settings.api_key}",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                return self._parse_structured_completion(
                    response,
                    latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
                )
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
                    f"model request failed: {type(exc).__name__}", retryable=True
                )
            except (
                KeyError,
                IndexError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ) as exc:
                error = ModelRequestError(
                    "model returned an invalid structured response", retryable=False
                )
                error.__cause__ = exc
            if not error.retryable or attempt >= self.settings.max_attempts:
                raise error
            await asyncio.sleep(0.25 * (2 ** (attempt - 1)))
        raise AssertionError("unreachable structured completion retry state")

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

        normalized_messages: list[dict[str, object]] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content")
            if role not in {"system", "user", "assistant"}:
                raise ValueError(f"unsupported message role: {role!r}")
            normalized_content: str | list[dict[str, object]]
            if isinstance(content, str):
                if not content.strip():
                    raise ValueError("message content must not be empty")
                normalized_content = content
            elif isinstance(content, list) and content:
                normalized_content = [
                    self._normalize_content_part(role, part) for part in content
                ]
            else:
                raise ValueError(
                    "message content must be a non-empty string or content-part list"
                )
            normalized_messages.append({"role": role, "content": normalized_content})

        return {
            "model": self.settings.model,
            "messages": normalized_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }

    def _parse_structured_completion(
        self, response: httpx.Response, *, latency_ms: int
    ) -> StructuredChatCompletion:
        body = response.json()
        choice = body["choices"][0]
        content = choice["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("structured completion content is empty")
        usage = body.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        finish_reason = choice.get("finish_reason")
        return StructuredChatCompletion(
            text=content,
            model=str(body.get("model") or self.settings.model),
            prompt_tokens=prompt_tokens if isinstance(prompt_tokens, int) else None,
            completion_tokens=(
                completion_tokens if isinstance(completion_tokens, int) else None
            ),
            finish_reason=finish_reason if isinstance(finish_reason, str) else None,
            latency_ms=latency_ms,
        )

    def _normalize_content_part(
        self,
        role: str,
        part: object,
    ) -> dict[str, object]:
        if not isinstance(part, dict):
            raise TypeError("message content parts must be objects")
        part_type = part.get("type")
        if part_type == "text":
            if set(part) != {"type", "text"}:
                raise ValueError("text content parts contain unsupported fields")
            text = part.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("text content parts must not be empty")
            return {"type": "text", "text": text}
        if part_type == "image_url":
            if role != "user":
                raise ValueError("image content parts are supported only for user messages")
            if not self.supports_vision:
                raise ValueError("image content requires a vision-capable model")
            if set(part) != {"type", "image_url"}:
                raise ValueError("image content parts contain unsupported fields")
            image_url = part.get("image_url")
            if not isinstance(image_url, dict) or set(image_url) != {"url"}:
                raise ValueError("image_url must contain only a url")
            url = image_url.get("url")
            self._validate_image_data_url(url)
            return {"type": "image_url", "image_url": {"url": url}}
        raise ValueError(f"unsupported message content part: {part_type!r}")

    @staticmethod
    def _validate_image_data_url(url: object) -> None:
        if not isinstance(url, str):
            raise TypeError("image URL must be a string")
        prefix, separator, encoded = url.partition(",")
        if (
            not separator
            or prefix
            not in {
                "data:image/png;base64",
                "data:image/jpeg;base64",
                "data:image/webp;base64",
            }
            or not encoded
        ):
            raise ValueError("image URL must be a supported base64 data URL")
        try:
            base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise ValueError("image URL contains invalid base64 data") from exc

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

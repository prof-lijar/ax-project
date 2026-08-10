import json

import httpx
import pytest
from ax_integrations import (
    ModelConfigurationError,
    ModelRequestError,
    OpenAICompatibleChatModel,
    OpenAICompatibleSettings,
)


def test_settings_accept_requested_environment_names_without_exposing_key() -> None:
    settings = OpenAICompatibleSettings.from_env(
        {
            "URL": "http://model.internal:8000/v1",
            "MODEL": "gemma-4-31b",
            "OPENAI_API_KEY": "secret-token",
        }
    )

    assert settings.completions_url == (
        "http://model.internal:8000/v1/chat/completions"
    )
    assert settings.model == "gemma-4-31b"
    assert "secret-token" not in repr(settings)


def test_settings_report_missing_environment() -> None:
    with pytest.raises(ModelConfigurationError, match="OPENAI_API_KEY"):
        OpenAICompatibleSettings.from_env(
            {"URL": "http://model.internal:8000/v1", "MODEL": "gemma-4-31b"}
        )


@pytest.mark.asyncio
async def test_chat_model_streams_openai_compatible_response() -> None:
    observed: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        observed["authorization"] = request.headers["authorization"]
        observed["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
                b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
                b"data: [DONE]\n\n"
            ),
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    model = OpenAICompatibleChatModel(
        OpenAICompatibleSettings(
            base_url="http://model.internal:8000/v1",
            model="gemma-4-31b",
            api_key="secret-token",
            max_attempts=1,
        ),
        client=client,
    )

    try:
        response = await model.complete(
            [{"role": "user", "content": "Explain concurrency"}]
        )
    finally:
        await client.aclose()

    assert response == "Hello world"
    assert observed["authorization"] == "Bearer secret-token"
    assert observed["payload"] == {
        "model": "gemma-4-31b",
        "messages": [{"role": "user", "content": "Explain concurrency"}],
        "max_tokens": 500,
        "temperature": 0.7,
        "stream": True,
    }


@pytest.mark.asyncio
async def test_chat_model_classifies_permanent_http_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    model = OpenAICompatibleChatModel(
        OpenAICompatibleSettings(
            base_url="http://model.internal:8000/v1",
            model="gemma-4-31b",
            api_key="secret-token",
            max_attempts=1,
        ),
        client=client,
    )

    try:
        with pytest.raises(ModelRequestError) as exc_info:
            await model.complete([{"role": "user", "content": "hello"}])
    finally:
        await client.aclose()

    assert exc_info.value.status_code == 401
    assert exc_info.value.retryable is False
    assert "secret-token" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_chat_model_retries_transient_failure_before_content() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                b'data: {"choices":[{"delta":{"content":"recovered"}}]}\n\n'
                b"data: [DONE]\n\n"
            ),
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    model = OpenAICompatibleChatModel(
        OpenAICompatibleSettings(
            base_url="http://model.internal:8000/v1",
            model="gemma-4-31b",
            api_key="secret-token",
            max_attempts=2,
        ),
        client=client,
    )

    try:
        response = await model.complete([{"role": "user", "content": "hello"}])
    finally:
        await client.aclose()

    assert response == "recovered"
    assert attempts == 2

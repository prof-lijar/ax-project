import json

import httpx
import pytest
from ax_integrations import (
    RagSearchClient,
    RagSearchConfigurationError,
    RagSearchError,
    RagSearchSettings,
)


def _payload() -> dict[str, object]:
    return {
        "results": [
            {
                "id": 10,
                "similarity": 0.75,
                "context": "first context",
                "document_id": 2,
                "source_type": "file",
                "source_name": "first.pdf",
                "chunk_index": 3,
                "source_start_character": 100,
                "source_end_character": 200,
                "token_count": 80,
            },
            {
                "id": 4,
                "similarity": 0.5,
                "context": "legacy context",
                "document_id": None,
                "source_type": None,
                "source_name": None,
                "chunk_index": None,
                "source_start_character": None,
                "source_end_character": None,
                "token_count": None,
            },
        ],
        "timing_ms": {
            "query_embedding": 1.0,
            "database_search": 2.0,
            "total": 3.0,
        },
    }


@pytest.mark.asyncio
async def test_rag_client_uses_exact_read_only_query_and_preserves_order() -> None:
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["query"] = request.url.params.get("query")
        captured["top_k"] = request.url.params.get("top_k")
        return httpx.Response(200, json=_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = RagSearchClient(
            RagSearchSettings(base_url="http://rag.internal:8765"),
            client=http_client,
        )
        response = await client.search("원본 질문 + PostgreSQL", top_k=5)

    assert captured == {
        "method": "GET",
        "path": "/rag/v1/search",
        "query": "원본 질문 + PostgreSQL",
        "top_k": "5",
    }
    assert [result.id for result in response.results] == [10, 4]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, text="private detail"),
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"results": []}),
    ],
)
async def test_rag_client_sanitizes_service_and_contract_failures(
    response: httpx.Response,
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return response

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = RagSearchClient(
            RagSearchSettings(base_url="http://rag.internal:8765"),
            client=http_client,
        )
        with pytest.raises(
            RagSearchError,
            match=r"^RAG retrieval is temporarily unavailable\.$",
        ):
            await client.search("question")


def test_rag_settings_require_credential_free_environment_url(monkeypatch) -> None:
    monkeypatch.delenv("RAG_SERVER_BASE_URL", raising=False)
    with pytest.raises(RagSearchConfigurationError, match="required"):
        RagSearchSettings.from_env()

    monkeypatch.setenv("RAG_SERVER_BASE_URL", "https://user:secret@rag.example")
    with pytest.raises(RagSearchConfigurationError, match="credential-free"):
        RagSearchSettings.from_env()


def test_rag_response_contract_rejects_unknown_fields() -> None:
    payload = _payload()
    payload["secret"] = "must-not-cross"

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps(payload).encode())

    async def exercise() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = RagSearchClient(
                RagSearchSettings(base_url="http://rag.internal"),
                client=http_client,
            )
            with pytest.raises(RagSearchError):
                await client.search("question")

    import asyncio

    asyncio.run(exercise())

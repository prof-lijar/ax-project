import asyncio
import json

import pytest
from ax_contracts import (
    WebFetchInput,
    WebFetchOutput,
    WebSearchInput,
    WebSearchOutput,
    WebSearchResult,
)
from ax_tools import ToolPolicy, create_web_fetch_tool, create_web_search_tool
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode


class FakeSearchExecutor:
    async def search(self, input: WebSearchInput) -> WebSearchOutput:
        return WebSearchOutput(
            original_query=input.query,
            results=[
                WebSearchResult(
                    source_id="src_0123456789abcdef",
                    title="Official docs",
                    url="https://example.com/docs",
                    domain="example.com",
                    snippet="Documentation",
                    engines=["test"],
                )
            ],
        )


class FakeFetchExecutor:
    async def fetch(self, input: WebFetchInput) -> WebFetchOutput:
        return WebFetchOutput(
            source_id="src_0123456789abcdef",
            final_url=input.url,
            title="Official docs",
            text="Verified page content",
            content_type="text/html",
            retrieved_at="2026-08-12T00:00:00Z",
        )


class SafeFailure(RuntimeError):
    error_code = "search_unavailable"
    safe_message = "search service is unavailable"
    retryable = True


class FailingSearchExecutor:
    async def search(self, input: WebSearchInput) -> WebSearchOutput:
        del input
        raise SafeFailure("internal detail that must not escape")


class CancellingSearchExecutor:
    async def search(self, input: WebSearchInput) -> WebSearchOutput:
        del input
        raise asyncio.CancelledError


@pytest.mark.asyncio
async def test_web_tools_are_compatible_with_tool_node_and_preserve_artifact() -> None:
    search_tool = create_web_search_tool(
        FakeSearchExecutor(),
        ToolPolicy(allowed_tools=frozenset({"web_search"})),
    )
    builder = StateGraph(MessagesState)
    builder.add_node("tools", ToolNode([search_tool]))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    graph = builder.compile()

    result = await graph.ainvoke(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "web_search",
                            "args": {"query": "LangGraph"},
                            "id": "call-1",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        }
    )

    tool_message = result["messages"][-1]
    content = json.loads(tool_message.content)
    assert content["status"] == "succeeded"
    assert content["data"]["results"][0]["title"] == "Official docs"
    assert tool_message.artifact["original_query"] == "LangGraph"


@pytest.mark.asyncio
async def test_web_fetch_tool_returns_structured_untrusted_content() -> None:
    tool = create_web_fetch_tool(
        FakeFetchExecutor(),
        ToolPolicy(allowed_tools=frozenset({"web_fetch"})),
    )
    result = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "web_fetch",
            "id": "call-2",
            "args": {"url": "https://example.com/docs"},
        }
    )
    content = json.loads(result.content)
    assert content["data"]["content_is_untrusted"] is True
    assert result.artifact["text"] == "Verified page content"


@pytest.mark.asyncio
async def test_web_tool_policy_denial_is_safe_and_executor_is_not_called() -> None:
    tool = create_web_search_tool(FakeSearchExecutor(), ToolPolicy())
    result = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "web_search",
            "id": "call-3",
            "args": {"query": "LangGraph"},
        }
    )
    content = json.loads(result.content)
    assert content == {
        "status": "failed",
        "error": {
            "code": "tool_denied",
            "message": "web tool is not authorized",
            "retryable": False,
        },
    }


@pytest.mark.asyncio
async def test_web_tool_validation_failure_is_safe() -> None:
    tool = create_web_search_tool(
        FakeSearchExecutor(),
        ToolPolicy(allowed_tools=frozenset({"web_search"})),
    )
    result = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "web_search",
            "id": "call-invalid",
            "args": {"query": "", "unknown": "must not cross"},
        }
    )
    content = json.loads(result.content)
    assert content["error"] == {
        "code": "invalid_tool_input",
        "message": "web tool input is invalid",
        "retryable": False,
    }


@pytest.mark.asyncio
async def test_web_tool_normalizes_expected_failure_without_internal_detail() -> None:
    tool = create_web_search_tool(
        FailingSearchExecutor(),
        ToolPolicy(allowed_tools=frozenset({"web_search"})),
    )
    result = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "web_search",
            "id": "call-4",
            "args": {"query": "LangGraph"},
        }
    )
    content = json.loads(result.content)
    assert content["error"] == {
        "code": "search_unavailable",
        "message": "search service is unavailable",
        "retryable": True,
    }
    assert "internal detail" not in result.content


@pytest.mark.asyncio
async def test_web_tool_propagates_cancellation() -> None:
    tool = create_web_search_tool(
        CancellingSearchExecutor(),
        ToolPolicy(allowed_tools=frozenset({"web_search"})),
    )
    with pytest.raises(asyncio.CancelledError):
        await tool.ainvoke({"query": "LangGraph"})


@pytest.mark.asyncio
async def test_web_tool_idempotency_is_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = []

    def capture(request, policy) -> None:  # type: ignore[no-untyped-def]
        del policy
        requests.append(request)

    monkeypatch.setattr("ax_tools.web.authorize", capture)
    tool = create_web_search_tool(
        FakeSearchExecutor(),
        ToolPolicy(allowed_tools=frozenset({"web_search"})),
    )
    await tool.ainvoke({"query": "LangGraph", "allowed_domains": ["example.com"]})
    await tool.ainvoke({"allowed_domains": ["example.com"], "query": "LangGraph"})

    assert len(requests) == 2
    assert requests[0].idempotency_key == requests[1].idempotency_key
    assert requests[0].idempotency_key.startswith("web_search:")

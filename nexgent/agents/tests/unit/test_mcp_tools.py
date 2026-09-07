import json

import pytest
from ax_contracts import McpToolCallResult, McpToolDefinition
from ax_tools import (
    McpToolConfigurationError,
    ToolPolicy,
    create_mcp_tools,
    mcp_tool_name,
)


class FakeMcpExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_tool(
        self, tool_name: str, arguments: dict[str, object]
    ) -> McpToolCallResult:
        self.calls.append((tool_name, arguments))
        return McpToolCallResult(
            server_name="db_mcp_server",
            tool_name=tool_name,
            content=[{"type": "text", "text": "one row"}],
            structured_content={"rows": [{"id": arguments["row_id"]}]},
        )


class SafeFailure(RuntimeError):
    error_code = "mcp_unavailable"
    safe_message = "MCP server is unavailable"
    retryable = True


class FailingMcpExecutor:
    async def call_tool(
        self, tool_name: str, arguments: dict[str, object]
    ) -> McpToolCallResult:
        del tool_name, arguments
        raise SafeFailure("secret internal failure")


def definition(*, risk: str | None = "read") -> McpToolDefinition:
    return McpToolDefinition(
        server_name="db_mcp_server",
        name="query.data",
        description="Retrieve one bounded row.",
        input_schema={
            "type": "object",
            "properties": {"row_id": {"type": "integer"}},
            "required": ["row_id"],
            "additionalProperties": False,
        },
        risk=risk,
    )


@pytest.mark.asyncio
async def test_mcp_tool_is_namespaced_authorized_and_returns_untrusted_artifact() -> (
    None
):
    executor = FakeMcpExecutor()
    public_name = "mcp__db_mcp_server__query_data"
    tool = create_mcp_tools(
        [definition()],
        executor,
        ToolPolicy(allowed_tools=frozenset({public_name})),
    )[0]

    result = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": public_name,
            "id": "call-1",
            "args": {"row_id": 7},
        }
    )

    content = json.loads(result.content)
    assert tool.name == public_name
    assert executor.calls == [("query.data", {"row_id": 7})]
    assert content["status"] == "succeeded"
    assert result.artifact["content_is_untrusted"] is True
    assert result.artifact["structured_content"] == {"rows": [{"id": 7}]}


@pytest.mark.asyncio
async def test_mcp_tool_policy_denial_prevents_remote_call() -> None:
    executor = FakeMcpExecutor()
    tool = create_mcp_tools([definition()], executor, ToolPolicy())[0]

    result = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": tool.name,
            "id": "call-denied",
            "args": {"row_id": 7},
        }
    )

    assert json.loads(result.content)["error"]["code"] == "tool_denied"
    assert executor.calls == []


@pytest.mark.asyncio
async def test_mcp_tool_validates_discovered_json_schema() -> None:
    executor = FakeMcpExecutor()
    tool = create_mcp_tools(
        [definition()],
        executor,
        ToolPolicy(allowed_tools=frozenset({"mcp__db_mcp_server__query_data"})),
    )[0]

    result = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": tool.name,
            "id": "call-invalid",
            "args": {"row_id": "not-an-integer", "unknown": True},
        }
    )

    assert json.loads(result.content)["error"]["code"] == "invalid_tool_input"
    assert executor.calls == []


def test_unclassified_mcp_tool_is_not_exposed() -> None:
    with pytest.raises(McpToolConfigurationError, match="risk is not classified"):
        create_mcp_tools([definition(risk=None)], FakeMcpExecutor(), ToolPolicy())


@pytest.mark.asyncio
async def test_mcp_tool_normalizes_integration_failure_without_internal_detail() -> (
    None
):
    public_name = "mcp__db_mcp_server__query_data"
    tool = create_mcp_tools(
        [definition()],
        FailingMcpExecutor(),
        ToolPolicy(allowed_tools=frozenset({public_name})),
    )[0]

    result = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": public_name,
            "id": "call-failed",
            "args": {"row_id": 1},
        }
    )

    content = json.loads(result.content)
    assert content["error"] == {
        "code": "mcp_unavailable",
        "message": "MCP server is unavailable",
        "retryable": True,
    }
    assert "secret internal failure" not in result.content


def test_mcp_tool_name_is_stable_and_provider_safe() -> None:
    assert mcp_tool_name("db_mcp_server", "query.data") == (
        "mcp__db_mcp_server__query_data"
    )
    assert len(mcp_tool_name("db_mcp_server", "x" * 200)) <= 128

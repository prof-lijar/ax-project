from datetime import date
from typing import Any

import pytest
from ax_contracts import McpToolCallResult, McpToolDefinition

from workflows.weekly_report.repository import (
    QUERY_DATA_TOOL,
    McpWeeklyWardRiskRepository,
    McpWeeklyWardRiskSettings,
    PolicyEnforcedWeeklyReportMcpGateway,
    WeeklyWardRiskRepositoryError,
)


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((tool_name, arguments))
        columns = arguments["columns"]
        if columns == ["ward_id", "date"]:
            rows = [
                {"ward_id": ward_id, "date": "2026-08-03"}
                for ward_id in (101, 102, 103, 104)
            ]
            truncated = True
        else:
            rows = [
                {
                    "ward_id": ward_id,
                    "date": danger_date,
                    "first_at": f"{danger_date}T01:00:00+00:00",
                }
                for ward_id, danger_date in (
                    (101, "2026-07-29"),
                    (101, "2026-08-03"),
                    (102, "2026-08-04"),
                    (103, "2026-08-05"),
                )
            ]
            truncated = False
        return {
            "schema_name": "ansimk",
            "table_name": "analysis_warddangerdaily",
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "offset": 0,
            "duration_ms": 1.0,
            "warnings": [],
        }


class FakeMcpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    async def list_tools(self) -> list[McpToolDefinition]:
        return [
            McpToolDefinition(
                server_name="db_mcp_server",
                name=name,
                input_schema={"type": "object", "additionalProperties": True},
                risk="read",
            )
            for name in (QUERY_DATA_TOOL, "preview_table")
        ]

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> McpToolCallResult:
        self.calls.append((tool_name, arguments))
        return McpToolCallResult(
            server_name="db_mcp_server",
            tool_name=tool_name,
            structured_content={"tool": tool_name},
        )

    async def aclose(self) -> None:
        self.closed = True


class FakeRegistry:
    def __init__(self, client: FakeMcpClient) -> None:
        self.client = client

    def create_client(self, server_name: str) -> FakeMcpClient:
        assert server_name == "db_mcp_server"
        return self.client


@pytest.mark.asyncio
async def test_repository_selects_bounded_wards_then_loads_complete_histories() -> (
    None
):
    gateway = FakeGateway()
    repository = McpWeeklyWardRiskRepository(gateway=gateway)

    selection = await repository.load_week(
        week_start=date(2026, 8, 3), timezone="Asia/Seoul"
    )

    assert [window.ward_id for window in selection.windows] == [101, 102, 103]
    assert selection.selection_truncated is True
    assert len(gateway.calls) == 2
    discovery = gateway.calls[0][1]
    assert discovery["filters"] == [
        {"column": "date", "operator": "gte", "value": "2026-07-27"},
        {"column": "date", "operator": "lt", "value": "2026-08-10"},
    ]
    detail = gateway.calls[1][1]
    assert detail["filters"][-1] == {
        "column": "ward_id",
        "operator": "in",
        "value": [101, 102, 103],
    }


@pytest.mark.asyncio
async def test_gateway_exposes_only_query_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeMcpClient()
    monkeypatch.setattr(
        "workflows.weekly_report.repository.load_mcp_registry",
        lambda: FakeRegistry(client),
    )
    gateway = PolicyEnforcedWeeklyReportMcpGateway("db_mcp_server")

    result = await gateway.call(QUERY_DATA_TOOL, {"table": "safe"})

    assert result == {"tool": QUERY_DATA_TOOL}
    with pytest.raises(WeeklyWardRiskRepositoryError, match="not authorized"):
        await gateway.call("preview_table", {"table": "safe"})
    assert len(client.calls) == 1
    await gateway.aclose()
    assert client.closed is True


def test_settings_default_to_ansimk_danger_source_and_three_wards() -> None:
    settings = McpWeeklyWardRiskSettings.from_env({})

    assert settings.schema_name == "ansimk"
    assert settings.table_name == "analysis_warddangerdaily"
    assert settings.max_wards == 3


def test_settings_reject_unbounded_demo_selection() -> None:
    with pytest.raises(WeeklyWardRiskRepositoryError, match="configuration is invalid"):
        McpWeeklyWardRiskSettings.from_env({"WEEKLY_REPORT_MAX_WARDS": "1000"})

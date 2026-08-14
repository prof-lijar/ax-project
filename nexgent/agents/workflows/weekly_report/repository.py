"""Ward-risk repository port plus MCP and deterministic test implementations."""

from __future__ import annotations

import asyncio
import os
import re
from collections import defaultdict
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any, Protocol

from ax_contracts import McpToolCallResult
from ax_integrations import (
    McpConfigurationError,
    McpIntegrationError,
    McpServerClient,
    load_mcp_registry,
)
from ax_tools import (
    McpToolConfigurationError,
    ToolPolicy,
    create_mcp_tools,
    mcp_tool_name,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .models import (
    McpRowsResult,
    WardDangerDay,
    WardRiskSelection,
    WardRiskWindow,
)

DB_MCP_SERVER_NAME = "db_mcp_server"
QUERY_DATA_TOOL = "query_data"
DEFAULT_SCHEMA_NAME = "ansimk"
DEFAULT_TABLE_NAME = "analysis_warddangerdaily"
DISCOVERY_PAGE_SIZE = 100
MAX_DEMO_WARDS = 25
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$-]{0,127}$")
_DISCOVERY_COLUMNS = ("ward_id", "date")
_DETAIL_COLUMNS = ("ward_id", "date", "first_at")


class WeeklyWardRiskRepository(Protocol):
    async def load_week(
        self,
        *,
        week_start: date,
        timezone: str,
    ) -> WardRiskSelection: ...


class WeeklyWardRiskRepositoryError(RuntimeError):
    """Safe failure at the workflow's real-data boundary."""


class McpWeeklyWardRiskSettings(BaseModel):
    """MCP source and bounded demo-selection settings."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    server_name: str = Field(default=DB_MCP_SERVER_NAME, min_length=1, max_length=64)
    schema_name: str = Field(default=DEFAULT_SCHEMA_NAME, min_length=1, max_length=128)
    table_name: str = Field(default=DEFAULT_TABLE_NAME, min_length=1, max_length=128)
    max_wards: int = Field(default=3, ge=1, le=MAX_DEMO_WARDS)

    @field_validator("server_name", "schema_name", "table_name")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError("MCP database identifiers must be unqualified names")
        return value

    @classmethod
    def from_env(
        cls, environ: Mapping[str, str] | None = None
    ) -> McpWeeklyWardRiskSettings:
        values = os.environ if environ is None else environ
        try:
            return cls(
                server_name=(
                    values.get("WEEKLY_REPORT_MCP_SERVER") or DB_MCP_SERVER_NAME
                ),
                schema_name=(
                    values.get("WEEKLY_REPORT_MCP_SCHEMA") or DEFAULT_SCHEMA_NAME
                ),
                table_name=(
                    values.get("WEEKLY_REPORT_MCP_TABLE") or DEFAULT_TABLE_NAME
                ),
                max_wards=values.get("WEEKLY_REPORT_MAX_WARDS") or "3",
            )
        except ValidationError as exc:
            raise WeeklyWardRiskRepositoryError(
                "weekly ward-risk MCP source configuration is invalid"
            ) from exc


class WeeklyReportMcpGateway(Protocol):
    async def call(self, tool_name: str, arguments: dict[str, Any]) -> Any: ...


class PolicyEnforcedWeeklyReportMcpGateway:
    """Expose only the structured read tool owned by this repository."""

    def __init__(self, server_name: str) -> None:
        self.server_name = server_name
        self._client: McpServerClient | None = None
        self._tool: Any | None = None
        self._initialization_lock = asyncio.Lock()

    async def _get_tool(self) -> Any:
        if self._tool is not None:
            return self._tool
        async with self._initialization_lock:
            if self._tool is not None:
                return self._tool
            client: McpServerClient | None = None
            try:
                client = load_mcp_registry().create_client(self.server_name)
                definitions = await client.list_tools()
                selected = [item for item in definitions if item.name == QUERY_DATA_TOOL]
                if len(selected) != 1:
                    raise WeeklyWardRiskRepositoryError(
                        "weekly ward-risk MCP is missing required tool: query_data"
                    )
                public_name = mcp_tool_name(self.server_name, QUERY_DATA_TOOL)
                tools = create_mcp_tools(
                    selected,
                    client,
                    ToolPolicy(allowed_tools=frozenset({public_name})),
                )
            except WeeklyWardRiskRepositoryError:
                if client is not None:
                    await client.aclose()
                raise
            except (
                McpConfigurationError,
                McpIntegrationError,
                McpToolConfigurationError,
            ) as exc:
                if client is not None:
                    await client.aclose()
                raise WeeklyWardRiskRepositoryError(
                    "weekly ward-risk MCP is unavailable"
                ) from exc
            self._client = client
            self._tool = tools[0]
            return self._tool

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if tool_name != QUERY_DATA_TOOL:
            raise WeeklyWardRiskRepositoryError(
                f"weekly ward-risk MCP tool is not authorized: {tool_name}"
            )
        tool = await self._get_tool()
        message = await tool.ainvoke(
            {
                "type": "tool_call",
                "name": tool.name,
                "id": "weekly-report-query-data",
                "args": arguments,
            }
        )
        artifact = getattr(message, "artifact", None)
        if artifact is None:
            raise WeeklyWardRiskRepositoryError(
                "weekly ward-risk MCP query failed"
            )
        try:
            result = McpToolCallResult.model_validate(artifact)
        except ValidationError as exc:
            raise WeeklyWardRiskRepositoryError(
                "weekly ward-risk MCP returned an invalid result"
            ) from exc
        if result.is_error or result.structured_content is None:
            raise WeeklyWardRiskRepositoryError(
                "weekly ward-risk MCP query failed"
            )
        return result.structured_content

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            self._tool = None


class McpWeeklyWardRiskRepository:
    """Select a small ward subset and load complete two-week danger histories."""

    def __init__(
        self,
        settings: McpWeeklyWardRiskSettings | None = None,
        *,
        gateway: WeeklyReportMcpGateway | None = None,
    ) -> None:
        self.settings = settings or McpWeeklyWardRiskSettings.from_env()
        self._gateway = gateway

    def _get_gateway(self) -> WeeklyReportMcpGateway:
        if self._gateway is None:
            self._gateway = PolicyEnforcedWeeklyReportMcpGateway(
                self.settings.server_name
            )
        return self._gateway

    async def load_week(
        self,
        *,
        week_start: date,
        timezone: str,
    ) -> WardRiskSelection:
        del timezone
        window_start = week_start - timedelta(days=7)
        window_end = week_start + timedelta(days=7)
        discovery = await self._query_page(
            columns=_DISCOVERY_COLUMNS,
            filters=self._date_filters(window_start, window_end),
            limit=DISCOVERY_PAGE_SIZE,
        )
        ward_ids = sorted({self._ward_id(row) for row in discovery.rows})
        selected_ids = ward_ids[: self.settings.max_wards]
        if not selected_ids:
            raise WeeklyWardRiskRepositoryError(
                "weekly ward-risk source returned no danger records for this window"
            )

        detail = await self._query_page(
            columns=_DETAIL_COLUMNS,
            filters=[
                *self._date_filters(window_start, window_end),
                {"column": "ward_id", "operator": "in", "value": selected_ids},
            ],
            limit=DISCOVERY_PAGE_SIZE,
        )
        if detail.truncated:
            raise WeeklyWardRiskRepositoryError(
                "weekly ward-risk detail query exceeded its bounded page"
            )
        windows = self._build_windows(detail.rows, selected_ids)
        return WardRiskSelection(
            windows=windows,
            selection_truncated=(
                discovery.truncated or len(ward_ids) > self.settings.max_wards
            ),
        )

    async def _query_page(
        self,
        *,
        columns: tuple[str, ...],
        filters: list[dict[str, Any]],
        limit: int,
    ) -> McpRowsResult:
        arguments = {
            "schema": self.settings.schema_name,
            "table": self.settings.table_name,
            "columns": list(columns),
            "filters": filters,
            "sort": [
                {"column": "ward_id", "direction": "asc"},
                {"column": "date", "direction": "asc"},
            ],
            "limit": limit,
            "offset": 0,
        }
        try:
            page = McpRowsResult.model_validate(
                await self._get_gateway().call(QUERY_DATA_TOOL, arguments)
            )
        except ValidationError as exc:
            raise WeeklyWardRiskRepositoryError(
                "weekly ward-risk MCP returned an invalid row page"
            ) from exc
        if (
            page.schema_name != self.settings.schema_name
            or page.table_name != self.settings.table_name
            or page.offset != 0
        ):
            raise WeeklyWardRiskRepositoryError(
                "weekly ward-risk MCP returned rows from an unexpected source"
            )
        if not set(columns).issubset(page.columns):
            raise WeeklyWardRiskRepositoryError(
                "weekly ward-risk MCP omitted required result columns"
            )
        return page

    @staticmethod
    def _date_filters(window_start: date, window_end: date) -> list[dict[str, Any]]:
        return [
            {
                "column": "date",
                "operator": "gte",
                "value": window_start.isoformat(),
            },
            {
                "column": "date",
                "operator": "lt",
                "value": window_end.isoformat(),
            },
        ]

    @staticmethod
    def _ward_id(row: dict[str, Any]) -> int:
        try:
            ward_id = int(row["ward_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise WeeklyWardRiskRepositoryError(
                "weekly ward-risk MCP returned an invalid ward identity"
            ) from exc
        if ward_id < 1:
            raise WeeklyWardRiskRepositoryError(
                "weekly ward-risk MCP returned an invalid ward identity"
            )
        return ward_id

    @classmethod
    def _build_windows(
        cls,
        rows: list[dict[str, Any]],
        selected_ids: list[int],
    ) -> list[WardRiskWindow]:
        grouped: dict[int, list[WardDangerDay]] = defaultdict(list)
        try:
            for row in rows:
                ward_id = cls._ward_id(row)
                grouped[ward_id].append(
                    WardDangerDay(
                        ward_id=ward_id,
                        danger_date=row["date"],
                        first_detected_at=row["first_at"],
                    )
                )
            windows = [
                WardRiskWindow(
                    ward_id=ward_id,
                    display_name=f"관리 대상 {ward_id}",
                    records=sorted(
                        grouped[ward_id], key=lambda record: record.danger_date
                    ),
                )
                for ward_id in selected_ids
            ]
        except (KeyError, ValidationError) as exc:
            raise WeeklyWardRiskRepositoryError(
                "weekly ward-risk MCP returned invalid danger records"
            ) from exc
        return windows


class MockWeeklyWardRiskRepository:
    """Stable three-ward danger-day scenario for deterministic tests."""

    async def load_week(
        self,
        *,
        week_start: date,
        timezone: str,
    ) -> WardRiskSelection:
        del timezone
        previous_start = week_start - timedelta(days=7)
        patterns = (
            (101, (0,), (0, 2)),
            (102, (1, 3), (1,)),
            (103, (4,), (4,)),
        )
        windows = []
        for ward_id, previous_offsets, current_offsets in patterns:
            dates = [
                *(previous_start + timedelta(days=offset) for offset in previous_offsets),
                *(week_start + timedelta(days=offset) for offset in current_offsets),
            ]
            windows.append(
                WardRiskWindow(
                    ward_id=ward_id,
                    display_name=f"관리 대상 {ward_id}",
                    records=[
                        WardDangerDay(
                            ward_id=ward_id,
                            danger_date=danger_date,
                            first_detected_at=datetime.combine(
                                danger_date, datetime.min.time()
                            ),
                        )
                        for danger_date in dates
                    ],
                )
            )
        return WardRiskSelection(windows=windows, selection_truncated=False)


@lru_cache(maxsize=1)
def get_weekly_ward_risk_repository() -> WeeklyWardRiskRepository:
    return McpWeeklyWardRiskRepository()

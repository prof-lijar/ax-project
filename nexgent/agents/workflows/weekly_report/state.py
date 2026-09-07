"""Small reducer-backed state for ward report fan-out and aggregation."""

import operator
from typing import Annotated, Any, TypedDict


class WeeklyReportState(TypedDict, total=False):
    week_start: str
    timezone: str
    ward_ids: list[int] | None
    cursor: str | None
    limit: int
    week_end: str
    work_items: list[dict[str, Any]]
    report_items: Annotated[list[dict[str, Any]], operator.add]
    warning_items: Annotated[list[str], operator.add]
    schema_version: str
    status: str
    reports: list[dict[str, Any]]
    warnings: list[str]
    skipped: list[dict[str, Any]]
    next_cursor: str | None


class WardReportBranchState(TypedDict, total=False):
    week_start: str
    week_end: str
    timezone: str
    work_item: dict[str, Any]
    metrics: dict[str, Any]
    narrative: dict[str, Any]
    generation_mode: str
    generation: dict[str, Any]
    report_items: list[dict[str, Any]]
    warning_items: list[str]


class WardReportBranchOutputState(TypedDict, total=False):
    report_items: list[dict[str, Any]]
    warning_items: list[str]

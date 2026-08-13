"""Small reducer-backed state for batch fan-out and aggregation."""

import operator
from typing import Annotated, Any, TypedDict


class WeeklyReportState(TypedDict, total=False):
    week_start: str
    timezone: str
    week_end: str
    work_items: list[dict[str, Any]]
    report_items: Annotated[list[dict[str, Any]], operator.add]
    warning_items: Annotated[list[str], operator.add]
    schema_version: str
    status: str
    reports: list[dict[str, Any]]
    warnings: list[str]


class UserReportBranchState(TypedDict, total=False):
    week_start: str
    week_end: str
    timezone: str
    work_item: dict[str, Any]
    metrics: dict[str, Any]
    narrative: dict[str, Any]
    generation_mode: str
    report_items: list[dict[str, Any]]
    warning_items: list[str]


class UserReportBranchOutputState(TypedDict, total=False):
    report_items: list[dict[str, Any]]
    warning_items: list[str]

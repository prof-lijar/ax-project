"""Coordinator and isolated per-ward branch nodes."""

from datetime import date
from typing import Any

from ax_contracts import (
    WardWeeklyMetrics,
    WardWeeklyReportBatchResult,
    WeeklyReportRequest,
    WeeklyReportSourceResponse,
)
from ax_integrations import get_default_chat_model
from langgraph.config import get_stream_writer
from langgraph.types import Send

from .agents.reporter import generate_narrative
from .domain import build_fact_package, render_report
from .state import WardReportBranchState, WeeklyReportState
from .tools import get_weekly_report_source_repository


async def validate_request(state: WeeklyReportState) -> dict[str, Any]:
    request = _interactive_request(state)
    get_stream_writer()(
        {"event": "batch_started", "week_start": request.week_start.isoformat()}
    )
    return request.model_dump(mode="json") | {"week_end": request.week_end.isoformat()}


async def load_source_data(state: WeeklyReportState) -> dict[str, Any]:
    request = _interactive_request(state)
    source = WeeklyReportSourceResponse.model_validate(
        await get_weekly_report_source_repository().load(request)
    )
    if source.week_start != request.week_start or source.timezone != request.timezone:
        raise ValueError("weekly-report source returned a mismatched period")
    ward_ids = [item.ward_id for item in source.items]
    if ward_ids != sorted(set(ward_ids)):
        raise ValueError("weekly-report source returned duplicate or unordered wards")
    get_stream_writer()(
        {
            "event": "risk_data_loaded",
            "ward_count": len(source.items),
            "selection_truncated": source.next_cursor is not None,
        }
    )
    return {
        "work_items": [item.model_dump(mode="json") for item in source.items],
        "warning_items": source.warnings,
        "skipped": [item.model_dump(mode="json") for item in source.skipped],
        "next_cursor": source.next_cursor,
    }


def _interactive_request(state: WeeklyReportState) -> WeeklyReportRequest:
    request = WeeklyReportRequest.model_validate(
        {
            "week_start": state.get("week_start"),
            "timezone": state.get("timezone", "Asia/Seoul"),
            "ward_ids": state.get("ward_ids"),
            "cursor": state.get("cursor"),
            "limit": state.get("limit", 25),
        }
    )
    if request.limit > 25:
        raise ValueError("interactive weekly-report limit must not exceed 25")
    return request


async def fan_out_wards(state: WeeklyReportState) -> str | list[Send]:
    if not state.get("work_items"):
        return "aggregate_reports"
    common = {
        "week_start": state["week_start"],
        "week_end": state["week_end"],
        "timezone": state["timezone"],
    }
    return [
        Send("build_ward_report", {**common, "work_item": work_item})
        for work_item in state["work_items"]
    ]


async def calculate_metrics(state: WardReportBranchState) -> dict[str, Any]:
    metrics = WardWeeklyMetrics.model_validate(state["work_item"])
    if metrics.week_start != date.fromisoformat(state["week_start"]):
        raise ValueError("ward metrics do not match the branch period")
    return {"metrics": metrics.model_dump(mode="json")}


async def generate_korean_narrative(state: WardReportBranchState) -> dict[str, Any]:
    metrics = WardWeeklyMetrics.model_validate(state["metrics"])
    facts = build_fact_package(metrics)
    narrative, generation_mode, generation = await generate_narrative(
        get_default_chat_model(), facts
    )
    warnings = []
    if generation_mode == "template_fallback":
        warnings.append(
            f"ward-{metrics.ward_id}: model_narrative_unavailable; template fallback used"
        )
        get_stream_writer()({"event": "ward_report_fallback"})
    return {
        "narrative": narrative.model_dump(mode="json"),
        "generation_mode": generation_mode,
        "generation": generation.model_dump(mode="json"),
        "warning_items": warnings,
    }


async def compose_markdown_report(state: WardReportBranchState) -> dict[str, Any]:
    from ax_contracts import NarrativeGenerationMetadata, WeeklyNarrative

    metrics = WardWeeklyMetrics.model_validate(state["metrics"])
    report = render_report(
        metrics,
        WeeklyNarrative.model_validate(state["narrative"]),
        state["generation_mode"],
        NarrativeGenerationMetadata.model_validate(state["generation"]),
    )
    get_stream_writer()(
        {"event": "ward_report_ready", "generation_mode": report.generation_mode}
    )
    return {"report_items": [report.model_dump(mode="json")]}


async def aggregate_reports(state: WeeklyReportState) -> dict[str, Any]:
    reports = sorted(state.get("report_items", []), key=lambda item: item["ward_id"])
    result = WardWeeklyReportBatchResult.model_validate(
        {
            "status": "completed",
            "week_start": state["week_start"],
            "week_end": state["week_end"],
            "timezone": state["timezone"],
            "reports": reports,
            "skipped": state.get("skipped", []),
            "next_cursor": state.get("next_cursor"),
            "warnings": sorted(state.get("warning_items", [])),
        }
    )
    get_stream_writer()(
        {
            "event": "batch_completed",
            "report_count": len(result.reports),
            "fallback_count": sum(
                report.generation_mode == "template_fallback" for report in result.reports
            ),
        }
    )
    return result.model_dump(mode="json")

"""Coordinator, ward metrics, narrative, rendering, and aggregation nodes."""

import json
from datetime import date, timedelta
from typing import Any

from ax_contracts import (
    WardWeeklyMetricDelta,
    WardWeeklyMetrics,
    WardWeeklyMetricSnapshot,
    WardWeeklyReportBatchResult,
    WeeklyReportRequest,
)
from ax_integrations import ModelRequestError, get_default_chat_model
from langgraph.config import get_stream_writer
from langgraph.types import Send

from .models import KoreanNarrative, WardRiskWindow
from .prompts import build_narrative_messages
from .rendering import build_fallback_narrative, render_report
from .repository import get_weekly_ward_risk_repository
from .state import WardReportBranchState, WeeklyReportState

NARRATIVE_MAX_TOKENS = 600


async def validate_request(state: WeeklyReportState) -> dict[str, Any]:
    request = WeeklyReportRequest.model_validate(
        {
            "week_start": state.get("week_start"),
            "timezone": state.get("timezone", "Asia/Seoul"),
        }
    )
    get_stream_writer()(
        {"event": "batch_started", "week_start": request.week_start.isoformat()}
    )
    return {
        "week_start": request.week_start.isoformat(),
        "week_end": request.week_end.isoformat(),
        "timezone": request.timezone,
    }


async def load_risk_windows(state: WeeklyReportState) -> dict[str, Any]:
    week_start = date.fromisoformat(state["week_start"])
    selection = await get_weekly_ward_risk_repository().load_week(
        week_start=week_start,
        timezone=state["timezone"],
    )
    windows = [WardRiskWindow.model_validate(window) for window in selection.windows]
    window_start = week_start - timedelta(days=7)
    window_end = week_start + timedelta(days=7)
    for window in windows:
        if any(
            record.danger_date < window_start or record.danger_date >= window_end
            for record in window.records
        ):
            raise ValueError("danger record falls outside the two-week window")
    ward_ids = [window.ward_id for window in windows]
    if len(ward_ids) != len(set(ward_ids)):
        raise ValueError("weekly ward-risk repository returned duplicate wards")

    warnings = (
        ["demo_source_selection_limited; only the first configured wards were used"]
        if selection.selection_truncated
        else []
    )
    get_stream_writer()(
        {
            "event": "risk_data_loaded",
            "ward_count": len(windows),
            "selection_truncated": selection.selection_truncated,
        }
    )
    return {
        "work_items": [window.model_dump(mode="json") for window in windows],
        "warning_items": warnings,
    }


async def fan_out_wards(state: WeeklyReportState) -> list[Send]:
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
    window = WardRiskWindow.model_validate(state["work_item"])
    week_start = date.fromisoformat(state["week_start"])
    previous_start = week_start - timedelta(days=7)
    week_end = week_start + timedelta(days=7)
    previous_days = {
        record.danger_date
        for record in window.records
        if previous_start <= record.danger_date < week_start
    }
    current_days = {
        record.danger_date
        for record in window.records
        if week_start <= record.danger_date < week_end
    }
    current = WardWeeklyMetricSnapshot(danger_days=len(current_days))
    previous = WardWeeklyMetricSnapshot(danger_days=len(previous_days))
    metrics = WardWeeklyMetrics(
        ward_id=window.ward_id,
        display_name=window.display_name,
        week_start=week_start,
        week_end=week_end,
        current=current,
        previous=previous,
        delta=WardWeeklyMetricDelta(
            danger_days=current.danger_days - previous.danger_days
        ),
    )
    return {"metrics": metrics.model_dump(mode="json")}


async def generate_korean_narrative(
    state: WardReportBranchState,
) -> dict[str, Any]:
    metrics = WardWeeklyMetrics.model_validate(state["metrics"])
    warning_items: list[str] = []
    try:
        response = await get_default_chat_model().complete(
            build_narrative_messages(metrics),
            max_tokens=NARRATIVE_MAX_TOKENS,
            temperature=0.1,
        )
        narrative = _parse_narrative(response)
        generation_mode = "llm"
    except (ModelRequestError, ValueError):
        narrative = build_fallback_narrative(metrics)
        generation_mode = "template_fallback"
        warning_items.append(
            f"ward-{metrics.ward_id}: model_narrative_unavailable; template fallback used"
        )
        get_stream_writer()({"event": "ward_report_fallback"})
    return {
        "narrative": narrative.model_dump(mode="json"),
        "generation_mode": generation_mode,
        "warning_items": warning_items,
    }


async def compose_markdown_report(
    state: WardReportBranchState,
) -> dict[str, Any]:
    metrics = WardWeeklyMetrics.model_validate(state["metrics"])
    narrative = KoreanNarrative.model_validate(state["narrative"])
    report = render_report(metrics, narrative, state["generation_mode"])
    get_stream_writer()(
        {
            "event": "ward_report_ready",
            "generation_mode": report.generation_mode,
        }
    )
    return {"report_items": [report.model_dump(mode="json")]}


async def aggregate_reports(state: WeeklyReportState) -> dict[str, Any]:
    reports = sorted(state.get("report_items", []), key=lambda item: item["ward_id"])
    warnings = sorted(state.get("warning_items", []))
    result = WardWeeklyReportBatchResult.model_validate(
        {
            "status": "completed",
            "week_start": state["week_start"],
            "week_end": state["week_end"],
            "timezone": state["timezone"],
            "reports": reports,
            "warnings": warnings,
        }
    )
    get_stream_writer()(
        {
            "event": "batch_completed",
            "report_count": len(result.reports),
            "fallback_count": sum(
                report.generation_mode == "template_fallback"
                for report in result.reports
            ),
        }
    )
    return result.model_dump(mode="json")


def _parse_narrative(response: str) -> KoreanNarrative:
    normalized = response.strip()
    if normalized.startswith("```") and normalized.endswith("```"):
        lines = normalized.splitlines()
        normalized = "\n".join(lines[1:-1]).strip()
    if not normalized:
        raise ValueError("model returned an empty narrative")
    return KoreanNarrative.model_validate(json.loads(normalized))

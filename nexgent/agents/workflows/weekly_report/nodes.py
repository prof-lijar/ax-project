"""Coordinator, calculation, narrative, rendering, and aggregation nodes."""

import json
from datetime import date, timedelta
from typing import Any

from ax_contracts import (
    UserWeeklyMetrics,
    WeeklyMetricDelta,
    WeeklyMetricSnapshot,
    WeeklyReportBatchResult,
    WeeklyReportRequest,
)
from ax_integrations import ModelRequestError, get_default_chat_model
from langgraph.config import get_stream_writer
from langgraph.types import Send

from .models import KoreanNarrative, UserActivityWindow
from .prompts import build_narrative_messages
from .rendering import build_fallback_narrative, render_report
from .repository import get_weekly_activity_repository
from .state import UserReportBranchState, WeeklyReportState

MAX_USERS_PER_BATCH = 100
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


async def load_mock_activity(state: WeeklyReportState) -> dict[str, Any]:
    week_start = date.fromisoformat(state["week_start"])
    repository = get_weekly_activity_repository()
    loaded = await repository.load_activity(
        week_start=week_start,
        timezone=state["timezone"],
    )
    users = [UserActivityWindow.model_validate(user) for user in loaded]
    if not users:
        raise ValueError("weekly activity repository returned no users")
    if len(users) > MAX_USERS_PER_BATCH:
        raise ValueError(f"weekly report batch exceeds {MAX_USERS_PER_BATCH} users")
    user_ids = [user.user_id for user in users]
    if len(user_ids) != len(set(user_ids)):
        raise ValueError("weekly activity repository returned duplicate users")

    window_start = week_start - timedelta(days=7)
    window_end = week_start + timedelta(days=7)
    for user in users:
        if any(
            record.activity_date < window_start or record.activity_date >= window_end
            for record in user.records
        ):
            raise ValueError("activity record falls outside the two-week window")

    return {
        "work_items": [user.model_dump(mode="json") for user in users],
    }


async def fan_out_users(state: WeeklyReportState) -> list[Send]:
    common = {
        "week_start": state["week_start"],
        "week_end": state["week_end"],
        "timezone": state["timezone"],
    }
    return [
        Send("build_user_report", {**common, "work_item": work_item})
        for work_item in state["work_items"]
    ]


async def calculate_metrics(state: UserReportBranchState) -> dict[str, Any]:
    user = UserActivityWindow.model_validate(state["work_item"])
    week_start = date.fromisoformat(state["week_start"])
    previous_start = week_start - timedelta(days=7)
    week_end = week_start + timedelta(days=7)
    previous = _snapshot(
        user,
        period_start=previous_start,
        period_end=week_start,
    )
    current = _snapshot(user, period_start=week_start, period_end=week_end)
    metrics = UserWeeklyMetrics(
        user_id=user.user_id,
        display_name=user.display_name,
        week_start=week_start,
        week_end=week_end,
        current=current,
        previous=previous,
        delta=WeeklyMetricDelta(
            assigned_tasks=current.assigned_tasks - previous.assigned_tasks,
            completed_tasks=current.completed_tasks - previous.completed_tasks,
            completion_rate_percentage_points=round(
                current.completion_rate_percent - previous.completion_rate_percent,
                1,
            ),
            focus_minutes=current.focus_minutes - previous.focus_minutes,
            active_days=current.active_days - previous.active_days,
            blockers_opened=current.blockers_opened - previous.blockers_opened,
            blockers_resolved=current.blockers_resolved - previous.blockers_resolved,
        ),
    )
    return {"metrics": metrics.model_dump(mode="json")}


async def generate_korean_narrative(
    state: UserReportBranchState,
) -> dict[str, Any]:
    metrics = UserWeeklyMetrics.model_validate(state["metrics"])
    warning_items: list[str] = []
    try:
        model = get_default_chat_model()
        response = await model.complete(
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
            f"{metrics.user_id}: model_narrative_unavailable; template fallback used"
        )
        get_stream_writer()(
            {
                "event": "user_report_fallback",
                "user_id": metrics.user_id,
            }
        )
    return {
        "narrative": narrative.model_dump(mode="json"),
        "generation_mode": generation_mode,
        "warning_items": warning_items,
    }


async def compose_markdown_report(
    state: UserReportBranchState,
) -> dict[str, Any]:
    metrics = UserWeeklyMetrics.model_validate(state["metrics"])
    narrative = KoreanNarrative.model_validate(state["narrative"])
    report = render_report(metrics, narrative, state["generation_mode"])
    get_stream_writer()(
        {
            "event": "user_report_ready",
            "user_id": report.user_id,
            "generation_mode": report.generation_mode,
        }
    )
    return {"report_items": [report.model_dump(mode="json")]}


async def aggregate_reports(state: WeeklyReportState) -> dict[str, Any]:
    reports = sorted(state.get("report_items", []), key=lambda item: item["user_id"])
    warnings = sorted(state.get("warning_items", []))
    result = WeeklyReportBatchResult.model_validate(
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


def _snapshot(
    user: UserActivityWindow,
    *,
    period_start: date,
    period_end: date,
) -> WeeklyMetricSnapshot:
    records = [
        record
        for record in user.records
        if period_start <= record.activity_date < period_end
    ]
    assigned = sum(record.assigned_tasks for record in records)
    completed = sum(record.completed_tasks for record in records)
    rate = round(completed / assigned * 100, 1) if assigned else 0.0
    return WeeklyMetricSnapshot(
        assigned_tasks=assigned,
        completed_tasks=completed,
        completion_rate_percent=rate,
        focus_minutes=sum(record.focus_minutes for record in records),
        active_days=sum(record.is_active for record in records),
        blockers_opened=sum(record.blockers_opened for record in records),
        blockers_resolved=sum(record.blockers_resolved for record in records),
    )


def _parse_narrative(response: str) -> KoreanNarrative:
    normalized = response.strip()
    if normalized.startswith("```") and normalized.endswith("```"):
        lines = normalized.splitlines()
        normalized = "\n".join(lines[1:-1]).strip()
    if not normalized:
        raise ValueError("model returned an empty narrative")
    return KoreanNarrative.model_validate(json.loads(normalized))

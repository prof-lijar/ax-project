from datetime import date
from typing import Any

import pytest
from ax_contracts import (
    NarrativeGenerationMetadata,
    WardWeeklyReportBatchResult,
    WeeklyReportRequest,
)
from ax_integrations import SlackMessageResult

from workflows.weekly_report.agents.reporter.fallback import build_fallback
from workflows.weekly_report.domain import build_fact_package, render_report
from workflows.weekly_report.slack_delivery import (
    SensitiveDeliveryApprovalRequired,
    deliver_weekly_report_batch,
)
from workflows.weekly_report.tools.source_repository import (
    MockWeeklyReportSourceRepository,
)


class FakeSlackDestination:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def send_to(self, **kwargs: Any) -> SlackMessageResult:
        self.calls.append(kwargs)
        return SlackMessageResult(
            success=True,
            channel_id="C0234567890",
            message_ts="123.456",
        )


async def build_batch() -> WardWeeklyReportBatchResult:
    source = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=date(2026, 8, 3), ward_ids=[101])
    )
    metrics = source.items[0]
    facts = build_fact_package(metrics)
    report = render_report(
        metrics,
        build_fallback(facts),
        "template_fallback",
        NarrativeGenerationMetadata(
            prompt_version="test",
            validation_status="fallback",
            fallback_reason="test_fixture",
        ),
    )
    return WardWeeklyReportBatchResult(
        status="completed",
        week_start=date(2026, 8, 3),
        week_end=date(2026, 8, 10),
        timezone="Asia/Seoul",
        reports=[report],
    )


@pytest.mark.asyncio
async def test_weekly_report_delivery_requires_explicit_human_approval() -> None:
    with pytest.raises(SensitiveDeliveryApprovalRequired):
        await deliver_weekly_report_batch(await build_batch(), FakeSlackDestination())


@pytest.mark.asyncio
async def test_weekly_report_delivery_uses_approved_default_destination() -> None:
    slack = FakeSlackDestination()
    batch = await build_batch()

    result = await deliver_weekly_report_batch(
        batch,
        slack,
        approved_sensitive_delivery=True,
    )

    assert result.success is True
    assert result.attempted == result.delivered == 1
    assert slack.calls[0]["destination"] == "default"
    assert slack.calls[0]["text"] == batch.reports[0].markdown
    assert slack.calls[0]["metadata"] == {
        "workflow": "ansimk_weekly_reporter",
        "ward_id": 101,
        "week_start": "2026-08-03",
    }

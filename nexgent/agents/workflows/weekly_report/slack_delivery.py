"""Explicit, human-approved Slack delivery for completed weekly reports."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from ax_contracts import WardWeeklyReportBatchResult
from ax_integrations import (
    SlackConfigurationError,
    SlackMessageResult,
    SlackService,
    SlackSettings,
)

from workflows.weekly_report.graph import graph


class SensitiveDeliveryApprovalRequired(PermissionError):
    """Weekly care reports require an explicit operator approval before delivery."""


class SlackDestination(Protocol):
    async def send_to(
        self,
        *,
        destination: str,
        text: str,
        thread_ts: str | None = None,
        blocks: list[dict[str, object]] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> SlackMessageResult: ...


@dataclass(frozen=True, slots=True)
class WeeklyReportDeliveryItem:
    ward_id: int
    result: SlackMessageResult


@dataclass(frozen=True, slots=True)
class WeeklyReportDeliveryResult:
    attempted: int
    delivered: int
    items: list[WeeklyReportDeliveryItem] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.attempted > 0 and self.delivered == self.attempted


Sleep = Callable[[float], Awaitable[None]]


async def deliver_weekly_report_batch(
    batch: WardWeeklyReportBatchResult,
    slack_service: SlackDestination,
    *,
    destination: str = "default",
    approved_sensitive_delivery: bool = False,
    inter_message_delay_seconds: float = 1.1,
    sleep: Sleep = asyncio.sleep,
) -> WeeklyReportDeliveryResult:
    """Deliver one already-validated report per message to an approved destination."""
    if not approved_sensitive_delivery:
        raise SensitiveDeliveryApprovalRequired(
            "weekly report Slack delivery requires explicit human approval"
        )
    if inter_message_delay_seconds < 0:
        raise ValueError("inter-message delay must not be negative")

    items: list[WeeklyReportDeliveryItem] = []
    for index, report in enumerate(batch.reports):
        result = await slack_service.send_to(
            destination=destination,
            text=report.markdown,
            metadata={
                "workflow": "ansimk_weekly_reporter",
                "ward_id": report.ward_id,
                "week_start": batch.week_start.isoformat(),
            },
        )
        items.append(WeeklyReportDeliveryItem(ward_id=report.ward_id, result=result))
        if index < len(batch.reports) - 1 and inter_message_delay_seconds:
            await sleep(inter_message_delay_seconds)

    return WeeklyReportDeliveryResult(
        attempted=len(items),
        delivered=sum(item.result.success for item in items),
        items=items,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="weekly-report-slack-delivery")
    parser.add_argument("--week-start", required=True, help="reporting Monday, YYYY-MM-DD")
    parser.add_argument("--timezone", default="Asia/Seoul")
    parser.add_argument("--ward-id", action="append", type=int, dest="ward_ids")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--destination", default="default")
    parser.add_argument(
        "--approve-sensitive-delivery",
        action="store_true",
        help="confirm that this care report may be delivered to the configured channel",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    if not args.approve_sensitive_delivery:
        raise SensitiveDeliveryApprovalRequired(
            "pass --approve-sensitive-delivery after reviewing the destination"
        )
    graph_result = await graph.ainvoke(
        {
            "week_start": args.week_start,
            "timezone": args.timezone,
            "ward_ids": args.ward_ids,
            "limit": args.limit,
        },
        # This is an operator-facing path that shares the interactive model
        # endpoint. Keep only one report generation in flight so Chat retains
        # an opportunity to enter the provider queue between reports.
        config={"max_concurrency": 1},
    )
    batch = WardWeeklyReportBatchResult.model_validate(graph_result)
    delivery = await deliver_weekly_report_batch(
        batch,
        SlackService(SlackSettings.from_env()),
        destination=args.destination,
        approved_sensitive_delivery=True,
    )
    print(
        json.dumps(
            {
                "success": delivery.success,
                "attempted": delivery.attempted,
                "delivered": delivery.delivered,
                "items": [
                    {
                        "ward_id": item.ward_id,
                        "success": item.result.success,
                        "channel_id": item.result.channel_id,
                        "message_ts": item.result.message_ts,
                        "error": item.result.error,
                    }
                    for item in delivery.items
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if delivery.success else 1


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return asyncio.run(_run(build_parser().parse_args(argv)))
    except (SlackConfigurationError, SensitiveDeliveryApprovalRequired) as exc:
        print(json.dumps({"success": False, "error": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SensitiveDeliveryApprovalRequired",
    "WeeklyReportDeliveryItem",
    "WeeklyReportDeliveryResult",
    "deliver_weekly_report_batch",
]

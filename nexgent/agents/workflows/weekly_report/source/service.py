"""Application service that builds bounded raw weekly snapshots."""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from ax_contracts import SkippedWard, WeeklyReportRequest, WeeklyReportSourceResponse
from ax_integrations import ReadOnlyDatabase

from .calculator import calculate_metrics
from .queries import (
    CANDIDATE_WARDS_SQL,
    DAILY_ROWS_SQL,
    DISPATCH_AGGREGATES_SQL,
    EXPLICIT_WARDS_SQL,
    RISK_AGGREGATES_SQL,
)


class SourceRequestError(ValueError):
    """Safe invalid cursor or source request error."""


class WeeklyReportSourceService:
    def __init__(self, database: ReadOnlyDatabase) -> None:
        self.database = database

    async def health(self) -> bool:
        return await self.database.health()

    async def build(self, request: WeeklyReportRequest) -> WeeklyReportSourceResponse:
        timezone = ZoneInfo(request.timezone)
        previous_start = request.week_start - timedelta(days=7)
        week_end = request.week_end
        previous_at = datetime.combine(previous_start, time.min, timezone)
        week_at = datetime.combine(request.week_start, time.min, timezone)
        end_at = datetime.combine(week_end, time.min, timezone)

        skipped: list[SkippedWard] = []
        next_cursor = None
        if request.ward_ids is not None:
            ward_rows = await self.database.fetch(EXPLICIT_WARDS_SQL, request.ward_ids)
            found = {int(row["ward_id"]) for row in ward_rows}
            skipped = [
                SkippedWard(ward_id=ward_id, reason="not_found")
                for ward_id in request.ward_ids
                if ward_id not in found
            ]
        else:
            after = self._decode_cursor(request) if request.cursor else 0
            ward_rows = await self.database.fetch(
                CANDIDATE_WARDS_SQL,
                after,
                request.limit + 1,
            )
            has_more = len(ward_rows) > request.limit
            ward_rows = ward_rows[: request.limit]
            if has_more and ward_rows:
                next_cursor = self._encode_cursor(
                    request, int(ward_rows[-1]["ward_id"])
                )

        ward_names = {
            int(row["ward_id"]): (
                str(row.get("full_name") or "").strip()
                or f"관리 대상 {int(row['ward_id'])}"
            )
            for row in ward_rows
        }
        if not ward_names:
            return WeeklyReportSourceResponse(
                week_start=request.week_start,
                week_end=week_end,
                timezone=request.timezone,
                skipped=skipped,
                next_cursor=next_cursor,
                warnings=["no_candidate_wards"],
            )

        ward_ids = sorted(ward_names)
        daily_rows, risk_rows, dispatch_rows = await asyncio.gather(
            self.database.fetch(DAILY_ROWS_SQL, ward_ids, previous_start, week_end),
            self.database.fetch(
                RISK_AGGREGATES_SQL,
                ward_ids,
                previous_at,
                week_at,
                end_at,
                request.timezone,
            ),
            self.database.fetch(
                DISPATCH_AGGREGATES_SQL, ward_ids, previous_at, week_at, end_at
            ),
        )
        items = calculate_metrics(
            ward_names=ward_names,
            week_start=request.week_start,
            daily_rows=daily_rows,
            risk_rows=risk_rows,
            dispatch_rows=dispatch_rows,
        )
        warnings = [
            f"ward-{item.ward_id}: incomplete_daily_coverage"
            for item in items
            if item.current.covered_days < 7
        ]
        return WeeklyReportSourceResponse(
            week_start=request.week_start,
            week_end=week_end,
            timezone=request.timezone,
            items=items,
            skipped=skipped,
            next_cursor=next_cursor,
            warnings=warnings,
        )

    def _encode_cursor(self, request: WeeklyReportRequest, last_ward_id: int) -> str:
        payload = json.dumps(
            {
                "last_ward_id": last_ward_id,
                "week_start": request.week_start.isoformat(),
                "timezone": request.timezone,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return base64.urlsafe_b64encode(payload).decode().rstrip("=")

    def _decode_cursor(self, request: WeeklyReportRequest) -> int:
        try:
            encoded = request.cursor or ""
            payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            value = json.loads(payload)
            if (
                value["week_start"] != request.week_start.isoformat()
                or value["timezone"] != request.timezone
            ):
                raise SourceRequestError("cursor does not match the request")
            last_ward_id = int(value["last_ward_id"])
            if last_ward_id < 1:
                raise ValueError
            return last_ward_id
        except SourceRequestError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SourceRequestError("cursor is invalid") from exc

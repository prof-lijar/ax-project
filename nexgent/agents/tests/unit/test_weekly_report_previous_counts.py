"""Saved report counts remain stable when historical daily summaries change."""

import json
from datetime import date

import pytest
from ax_contracts import (
    NarrativeGenerationMetadata,
    WeeklyNarrative,
    WeeklyReportRequest,
)
from ax_integrations import DatabaseUnavailable

from workflows.weekly_report.domain.activity_policy import assess_activity
from workflows.weekly_report.domain.rendering import render_report
from workflows.weekly_report.source.queries import (
    CANDIDATE_WARDS_SQL,
    DAILY_ROWS_SQL,
    EXPLICIT_WARDS_SQL,
    PREVIOUS_ACTIVITY_COUNTS_SQL,
    RISK_AGGREGATES_SQL,
)
from workflows.weekly_report.source.service import WeeklyReportSourceService


class CountDatabase:
    def __init__(self):
        self.calls = []
        self.saved = [
            {
                "ward_id": 10,
                "movement_count_total": "2278.0",
                "remote_control_count_total": "1123.0",
            },
            {
                "ward_id": 20,
                "movement_count_total": "50",
                "remote_control_count_total": "0",
            },
        ]
        self.daily = [
            {
                "ward_id": 10,
                "device_id": 1,
                "date": date(2026, 10, 19),
                "movement_count": 3002,
                "remote_control_count": 1606,
            },
            {
                "ward_id": 10,
                "device_id": 1,
                "date": date(2026, 10, 26),
                "movement_count": 2710,
                "remote_control_count": 1967,
            },
        ]
        for row in self.daily:
            for field in (
                "temperature",
                "humidity",
                "light",
                "temperature_count",
                "humidity_count",
                "light_count",
                "min_temperature",
                "max_temperature",
                "min_humidity",
                "max_humidity",
                "min_light",
                "max_light",
                "light_on_time_minutes",
                "wake_up_time",
                "sleep_time",
                "night_awake_count",
            ):
                row[field] = None

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        if query in (CANDIDATE_WARDS_SQL, EXPLICIT_WARDS_SQL):
            ids = args[0] if query == EXPLICIT_WARDS_SQL else [10, 20]
            return [{"ward_id": ward, "full_name": f"Ward {ward}"} for ward in ids]
        if query == PREVIOUS_ACTIVITY_COUNTS_SQL:
            return [row for row in self.saved if row["ward_id"] in args[0]]
        if query == DAILY_ROWS_SQL:
            return self.daily
        if query == RISK_AGGREGATES_SQL:
            return [
                {
                    "ward_id": 10,
                    "period_index": 0,
                    "danger_days": 2,
                    "risk_detected_count": 3,
                    "risk_resolved_count": 1,
                }
            ]
        return []


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit", [True, False])
async def test_saved_counts_drive_rendered_comparison_despite_changed_raw_data(
    explicit,
):
    database = CountDatabase()
    service = WeeklyReportSourceService(database)
    request = WeeklyReportRequest(
        week_start=date(2026, 10, 26),
        ward_ids=[10, 20] if explicit else None,
    )
    for changed_total in (3002, 9000):
        database.daily[0]["movement_count"] = changed_total
        database.daily[0]["remote_control_count"] = changed_total
        result = await service.build(request)
        first, second = result.items
        assert first.previous.movement_count_total == 2278
        assert first.previous.remote_control_count_total == 1123
        assert first.current.movement_count_total == 2710
        assert first.current.remote_control_count_total == 1967
        assert first.previous.danger_days == 2
        assert first.previous.risk_detected_count == 3
        assert first.delta.danger_days == -2
        assert second.previous.movement_count_total == 50
        assert second.previous.remote_control_count_total == 0
        assert not any("previous_activity" in warning for warning in result.warnings)
        report = render_report(
            first,
            WeeklyNarrative(
                headline="검증", analysis_text="", observations=[], suggestions=[]
            ),
            "template_fallback",
            NarrativeGenerationMetadata(
                prompt_version="saved-count-regression",
                validation_status="fallback",
            ),
        )
        activity = report.template_data.living_activity
        assert activity.activity_detection.metrics.previous_week == 2278
        assert activity.activity_detection.metrics.comparison_display == "119.0%"
        assert activity.remote_control_usage.metrics.previous_week == 1123
        assert activity.remote_control_usage.metrics.comparison_display == "175.2%"
        assert activity.remote_control_usage.status == "CAUTION"
    saved_calls = [
        args for query, args in database.calls if query == PREVIOUS_ACTIVITY_COUNTS_SQL
    ]
    assert saved_calls == [([10, 20], date(2026, 10, 19), date(2026, 10, 25))] * 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    [
        None,
        "null",
        '"123"',
        "true",
        "-1",
        "NaN",
        "Infinity",
        "{}",
        "[]",
        "bad-json",
        "1e999",
    ],
)
async def test_unavailable_or_invalid_saved_signal_never_falls_back_to_raw(value):
    database = CountDatabase()
    database.saved[0]["movement_count_total"] = value
    result = await WeeklyReportSourceService(database).build(
        WeeklyReportRequest(week_start=date(2026, 10, 26), ward_ids=[10])
    )
    metrics = result.items[0]
    assert metrics.previous.movement_count_total is None
    assert metrics.previous.remote_control_count_total == 1123
    assert metrics.current.movement_count_total == 2710
    assert assess_activity(metrics).movement.status == "UNAVAILABLE"
    assert "ward-10: previous_activity_counts_unavailable" in result.warnings


@pytest.mark.asyncio
@pytest.mark.parametrize("saved", [[], [{"ward_id": 10}]])
async def test_missing_report_or_fields_do_not_recalculate_previous_totals(saved):
    database = CountDatabase()
    database.saved = saved
    result = await WeeklyReportSourceService(database).build(
        WeeklyReportRequest(week_start=date(2026, 10, 26), ward_ids=[10])
    )
    assert result.items[0].previous.movement_count_total is None
    assert result.items[0].previous.remote_control_count_total is None
    assert "ward-10: previous_activity_counts_unavailable" in result.warnings


@pytest.mark.asyncio
async def test_zero_is_preserved_and_never_replaced_by_raw_count():
    database = CountDatabase()
    database.saved[0]["movement_count_total"] = json.dumps(0)
    result = await WeeklyReportSourceService(database).build(
        WeeklyReportRequest(week_start=date(2026, 10, 26), ward_ids=[10])
    )
    metrics = result.items[0]
    assert metrics.previous.movement_count_total == 0
    assert assess_activity(metrics).movement.ratio_percent is None
    assert not any("previous_activity" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_saved_report_database_failure_is_not_hidden_by_recalculation():
    class UnavailableDatabase(CountDatabase):
        async def fetch(self, query, *args):
            if query == PREVIOUS_ACTIVITY_COUNTS_SQL:
                raise DatabaseUnavailable("PostgreSQL query failed")
            return await super().fetch(query, *args)

    with pytest.raises(DatabaseUnavailable):
        await WeeklyReportSourceService(UnavailableDatabase()).build(
            WeeklyReportRequest(week_start=date(2026, 10, 26), ward_ids=[10])
        )

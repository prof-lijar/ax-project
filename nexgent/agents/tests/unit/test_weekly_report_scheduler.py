from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Self
from urllib.error import URLError

import pytest

from apps.weekly_report_scheduler.submit import (
    ScheduledSubmissionError,
    SchedulerConfigurationError,
    SchedulerSettings,
    build_job_payload,
    previous_completed_week_start,
    submit_scheduled_job,
)


class FakeResponse:
    status = 201

    def __init__(self, body: dict[str, object]) -> None:
        self.body = json.dumps(body).encode()

    def read(self, amount: int = -1) -> bytes:
        return self.body[:amount]

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_schedule_uses_previous_completed_monday_in_seoul() -> None:
    sunday_utc = datetime(2026, 9, 6, 18, 0, tzinfo=UTC)

    assert previous_completed_week_start(sunday_utc).isoformat() == "2026-08-31"


def test_payload_is_full_batch_and_idempotent_for_the_reporting_week() -> None:
    payload = build_job_payload(
        datetime(2026, 9, 6, 18, 0, tzinfo=UTC), max_reports=10_000
    )

    assert payload == {
        "week_start": "2026-08-31",
        "timezone": "Asia/Seoul",
        "max_reports": 10_000,
        "idempotency_key": "cron-weekly-report-2026-08-31",
    }


def test_submission_retries_transient_failure_with_same_request() -> None:
    calls = []
    delays = []
    events = []

    def opener(request, *, timeout):
        calls.append((request, timeout))
        if len(calls) == 1:
            raise URLError("offline")
        request_payload = json.loads(request.data)
        return FakeResponse(
            {
                "job_id": "8ff04888-a682-4704-8d27-3d5cd2cb26cb",
                "status": "pending",
                "week_start": request_payload["week_start"],
                "timezone": request_payload["timezone"],
                "max_reports": request_payload["max_reports"],
            }
        )

    result = submit_scheduled_job(
        SchedulerSettings(retry_delay_seconds=0.25),
        now=datetime(2026, 9, 6, 18, 0, tzinfo=UTC),
        opener=opener,
        sleeper=delays.append,
        log_event=events.append,
    )

    first_payload = json.loads(calls[0][0].data)
    second_payload = json.loads(calls[1][0].data)
    assert first_payload == second_payload
    assert result["status"] == "pending"
    assert delays == [0.25]
    assert [event["event"] for event in events] == [
        "weekly_report_schedule_retry",
        "weekly_report_schedule_submitted",
    ]


def test_submission_rejects_response_for_a_different_week() -> None:
    def opener(_request, *, timeout):
        del timeout
        return FakeResponse(
            {
                "job_id": "8ff04888-a682-4704-8d27-3d5cd2cb26cb",
                "status": "pending",
                "week_start": "2026-08-24",
                "timezone": "Asia/Seoul",
                "max_reports": 10_000,
            }
        )

    with pytest.raises(ScheduledSubmissionError, match="invalid_bulk_api_response"):
        submit_scheduled_job(
            SchedulerSettings(attempts=1),
            now=datetime(2026, 9, 6, 18, 0, tzinfo=UTC),
            opener=opener,
        )


def test_settings_reject_credentials_in_bulk_api_url() -> None:
    with pytest.raises(SchedulerConfigurationError, match="credential-free"):
        SchedulerSettings.from_env(
            {"WEEKLY_REPORT_BULK_API_URL": "http://user:secret@example.test"}
        )


def test_crontab_runs_every_monday_at_one_in_container_time() -> None:
    crontab = (
        Path(__file__).parents[2]
        / "apps"
        / "weekly_report_scheduler"
        / "crontab"
    ).read_text()

    assert any(line.startswith("0 1 * * 1 ") for line in crontab.splitlines())

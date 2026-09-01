import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.scout_schedule_models import (
    ScoutRunSuccess,
    ScoutScheduleCreateRequest,
    ScoutScheduleRecurrence,
    ScoutScheduleStatus,
)
from app.scout_schedule_repository import (
    DuplicateScheduleError,
    ScheduleTransitionError,
    ScoutScheduleRepository,
)

SEOUL = ZoneInfo("Asia/Seoul")


def schedule_request(minutes: int = 10) -> ScoutScheduleCreateRequest:
    run_at = (datetime.now(SEOUL) + timedelta(minutes=minutes)).replace(
        tzinfo=None, microsecond=0
    )
    return ScoutScheduleCreateRequest(
        topic=f"Scout topic {minutes}",
        keywords=["AI", "IoT"],
        run_at=run_at.isoformat(),
        timezone="Asia/Seoul",
    )


def scout_success() -> ScoutRunSuccess:
    started = datetime.now(UTC)
    return ScoutRunSuccess(
        run_id="run-123",
        status="success",
        started_at=started,
        completed_at=started + timedelta(seconds=12),
        duration_seconds=11.75,
        source_count=1,
        report="# Scout Report\n\nResult",
        sources=["https://example.com/source"],
        report_artifact="runs/run-123/report.md",
        log_artifact="runs/run-123/execution.jsonl",
    )


def recurring_request() -> ScoutScheduleCreateRequest:
    return ScoutScheduleCreateRequest(
        topic="Recurring Scout topic",
        keywords=["AI", "IoT"],
        recurrence="weekly",
        schedule_time="09:30:00",
        day_of_week="monday",
        timezone="Asia/Seoul",
    )


def test_create_read_list_update_and_multiple_schedules(tmp_path: Path) -> None:
    repository = ScoutScheduleRepository(tmp_path / "schedules.sqlite3")
    first = repository.create(schedule_request(10))
    second = repository.create(schedule_request(20))

    assert first.schedule_id != second.schedule_id
    assert {item.schedule_id for item in repository.list()} == {
        first.schedule_id,
        second.schedule_id,
    }

    running = repository.claim_pending(first.schedule_id)
    assert running is not None
    assert running.status is ScoutScheduleStatus.RUNNING

    result = scout_success()
    completed = repository.complete_success(first.schedule_id, result)
    assert completed.status is ScoutScheduleStatus.SUCCEEDED
    assert completed.scout_run == result


def test_persistence_survives_repository_recreation(tmp_path: Path) -> None:
    database_path = tmp_path / "schedules.sqlite3"
    request = schedule_request().model_copy(
        update={"additional_instructions": "Focus on public-sector cases."}
    )
    created = ScoutScheduleRepository(database_path).create(request)

    reloaded = ScoutScheduleRepository(database_path).get(created.schedule_id)

    assert reloaded == created
    assert reloaded.additional_instructions == "Focus on public-sector cases."


def test_cancellation_retains_audit_record_and_is_terminal(tmp_path: Path) -> None:
    repository = ScoutScheduleRepository(tmp_path / "schedules.sqlite3")
    created = repository.create(schedule_request())

    cancelled = repository.cancel_pending(created.schedule_id)

    assert cancelled.status is ScoutScheduleStatus.CANCELLED
    assert repository.get(created.schedule_id).status is ScoutScheduleStatus.CANCELLED
    with pytest.raises(ScheduleTransitionError):
        repository.cancel_pending(created.schedule_id)


def test_atomic_claim_prevents_duplicate_execution(tmp_path: Path) -> None:
    repository = ScoutScheduleRepository(tmp_path / "schedules.sqlite3")
    created = repository.create(schedule_request())

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: repository.claim_pending(created.schedule_id),
                range(2),
            )
        )

    assert sum(result is not None for result in results) == 1
    assert repository.get(created.schedule_id).status is ScoutScheduleStatus.RUNNING


def test_duplicate_pending_submission_is_rejected(tmp_path: Path) -> None:
    repository = ScoutScheduleRepository(tmp_path / "schedules.sqlite3")
    request = schedule_request()
    repository.create(request)

    with pytest.raises(DuplicateScheduleError):
        repository.create(request)


def test_additional_instructions_participate_in_pending_uniqueness(
    tmp_path: Path,
) -> None:
    repository = ScoutScheduleRepository(tmp_path / "schedules.sqlite3")
    request = schedule_request()

    first = repository.create(
        request.model_copy(
            update={"additional_instructions": "Focus on recent sources."}
        )
    )
    second = repository.create(
        request.model_copy(
            update={"additional_instructions": "Organize by competitor."}
        )
    )

    assert first.schedule_id != second.schedule_id


def test_stale_running_recovery_fails_without_retry_metadata(tmp_path: Path) -> None:
    repository = ScoutScheduleRepository(tmp_path / "schedules.sqlite3")
    created = repository.create(schedule_request())
    repository.claim_pending(created.schedule_id)

    recovered = repository.recover_stale_running()

    assert len(recovered) == 1
    assert recovered[0].status is ScoutScheduleStatus.FAILED
    assert recovered[0].error_code == "stale_running_recovery"
    assert recovered[0].scout_run is None


def test_additive_migration_preserves_existing_once_rows(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    request = schedule_request()
    now = datetime.now(UTC)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE scout_schedules (
                schedule_id TEXT PRIMARY KEY, topic TEXT NOT NULL,
                keywords_json TEXT NOT NULL, run_at_local TEXT NOT NULL,
                timezone TEXT NOT NULL, trigger_at_utc TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, dispatch_started_at TEXT,
                terminal_at TEXT, error_code TEXT, error_message TEXT,
                scout_run_json TEXT
            );
            """
        )
        connection.execute(
            """
            INSERT INTO scout_schedules (
                schedule_id, topic, keywords_json, run_at_local, timezone,
                trigger_at_utc, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "00000000-0000-4000-8000-000000000001",
                request.topic,
                json.dumps(request.keywords),
                request.run_at.isoformat(),
                request.timezone,
                request.trigger_at_utc.isoformat(),
                "pending",
                now.isoformat(),
                now.isoformat(),
            ),
        )

    record = ScoutScheduleRepository(database_path).get(
        "00000000-0000-4000-8000-000000000001"
    )

    assert record.recurrence is ScoutScheduleRecurrence.ONCE
    assert record.run_at == request.run_at
    assert record.schedule_time is None
    assert record.additional_instructions is None


def test_recurring_success_advances_and_retains_latest_result(tmp_path: Path) -> None:
    repository = ScoutScheduleRepository(tmp_path / "schedules.sqlite3")
    first_trigger = datetime(2026, 9, 7, 0, 30, tzinfo=UTC)
    created = repository.create(recurring_request(), trigger_at=first_trigger)
    repository.claim_pending(created.schedule_id)
    result = scout_success()

    completed = repository.complete_recurring_success(
        created.schedule_id,
        result,
        next_trigger_at=first_trigger + timedelta(days=7),
    )

    assert completed.status is ScoutScheduleStatus.PENDING
    assert completed.trigger_at == first_trigger + timedelta(days=7)
    assert completed.run_at.isoformat() == "2026-09-14T09:30:00"
    assert completed.scout_run == result

    cancelled = repository.cancel_pending(created.schedule_id)
    assert cancelled.status is ScoutScheduleStatus.CANCELLED
    assert cancelled.scout_run == result


def test_stale_recurring_run_recovers_active_without_retry(tmp_path: Path) -> None:
    repository = ScoutScheduleRepository(tmp_path / "schedules.sqlite3")
    created = repository.create(
        recurring_request(),
        trigger_at=datetime.now(UTC) + timedelta(days=1),
    )
    repository.claim_pending(created.schedule_id)

    recovered = repository.recover_stale_running()

    assert recovered[0].status is ScoutScheduleStatus.PENDING
    assert recovered[0].error_code == "stale_running_recovery"

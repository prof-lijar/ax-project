from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import TypeAdapter

from app.scout_schedule_models import (
    SEOUL_TIMEZONE,
    ScoutRunFailure,
    ScoutRunSuccess,
    ScoutRunTerminal,
    ScoutScheduleCreateRequest,
    ScoutScheduleRecord,
    ScoutScheduleRecurrence,
    ScoutScheduleStatus,
)

TERMINAL_ADAPTER = TypeAdapter(ScoutRunTerminal)


class ScheduleNotFoundError(LookupError):
    pass


class ScheduleTransitionError(RuntimeError):
    pass


class DuplicateScheduleError(RuntimeError):
    pass


class ScoutScheduleRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scout_schedules (
                    schedule_id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    keywords_json TEXT NOT NULL,
                    additional_instructions TEXT,
                    recurrence TEXT NOT NULL DEFAULT 'once',
                    run_at_local TEXT NOT NULL,
                    schedule_time_local TEXT,
                    day_of_week TEXT,
                    day_of_month INTEGER,
                    timezone TEXT NOT NULL,
                    trigger_at_utc TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    dispatch_started_at TEXT,
                    terminal_at TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    scout_run_json TEXT
                )
                """
            )
            existing_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(scout_schedules)"
                ).fetchall()
            }
            migrations = {
                "additional_instructions": (
                    "ALTER TABLE scout_schedules ADD COLUMN additional_instructions TEXT"
                ),
                "recurrence": (
                    "ALTER TABLE scout_schedules "
                    "ADD COLUMN recurrence TEXT NOT NULL DEFAULT 'once'"
                ),
                "schedule_time_local": (
                    "ALTER TABLE scout_schedules ADD COLUMN schedule_time_local TEXT"
                ),
                "day_of_week": (
                    "ALTER TABLE scout_schedules ADD COLUMN day_of_week TEXT"
                ),
                "day_of_month": (
                    "ALTER TABLE scout_schedules ADD COLUMN day_of_month INTEGER"
                ),
            }
            for column, statement in migrations.items():
                if column not in existing_columns:
                    connection.execute(statement)
            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_scout_schedules_status_trigger
                    ON scout_schedules(status, trigger_at_utc);

                DROP INDEX IF EXISTS idx_scout_schedules_pending_unique;

                CREATE UNIQUE INDEX idx_scout_schedules_pending_unique
                    ON scout_schedules(
                        topic,
                        keywords_json,
                        COALESCE(additional_instructions, ''),
                        recurrence,
                        run_at_local,
                        COALESCE(schedule_time_local, ''),
                        COALESCE(day_of_week, ''),
                        COALESCE(day_of_month, -1),
                        timezone
                    )
                    WHERE status = 'pending';
                """
            )

    def create(
        self,
        request: ScoutScheduleCreateRequest,
        *,
        schedule_id: UUID | None = None,
        trigger_at: datetime | None = None,
        now: datetime | None = None,
    ) -> ScoutScheduleRecord:
        identifier = schedule_id or uuid4()
        timestamp = _utc_now(now)
        resolved_trigger = _utc_now(trigger_at or request.trigger_at_utc)
        run_at = (
            request.run_at
            if request.run_at is not None
            else resolved_trigger.astimezone(SEOUL_TIMEZONE).replace(tzinfo=None)
        )
        keywords_json = _compact_json(request.keywords)
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO scout_schedules (
                        schedule_id, topic, keywords_json, additional_instructions,
                        recurrence, run_at_local, schedule_time_local, day_of_week,
                        day_of_month, timezone, trigger_at_utc, status, created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(identifier),
                        request.topic,
                        keywords_json,
                        request.additional_instructions,
                        request.recurrence.value,
                        run_at.isoformat(),
                        (
                            request.schedule_time.isoformat()
                            if request.schedule_time is not None
                            else None
                        ),
                        (
                            request.day_of_week.value
                            if request.day_of_week is not None
                            else None
                        ),
                        request.day_of_month,
                        request.timezone,
                        _iso(resolved_trigger),
                        ScoutScheduleStatus.PENDING.value,
                        _iso(timestamp),
                        _iso(timestamp),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if "pending_unique" in str(exc) or "UNIQUE constraint failed" in str(exc):
                raise DuplicateScheduleError(
                    "An identical pending Scout schedule already exists."
                ) from None
            raise
        return self.get(identifier)

    def get(self, schedule_id: UUID | str) -> ScoutScheduleRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM scout_schedules WHERE schedule_id = ?",
                (str(schedule_id),),
            ).fetchone()
        if row is None:
            raise ScheduleNotFoundError(str(schedule_id))
        return _row_to_record(row)

    def list(self) -> list[ScoutScheduleRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM scout_schedules
                ORDER BY created_at DESC, schedule_id DESC
                """
            ).fetchall()
        return [_row_to_record(row) for row in rows]

    def list_with_statuses(
        self, statuses: Iterable[ScoutScheduleStatus]
    ) -> list[ScoutScheduleRecord]:
        values = [status.value for status in statuses]
        if not values:
            return []
        placeholders = ", ".join("?" for _ in values)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM scout_schedules
                WHERE status IN ({placeholders})
                ORDER BY trigger_at_utc, schedule_id
                """,
                values,
            ).fetchall()
        return [_row_to_record(row) for row in rows]

    def claim_pending(
        self, schedule_id: UUID | str, *, now: datetime | None = None
    ) -> ScoutScheduleRecord | None:
        timestamp = _utc_now(now)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE scout_schedules
                SET status = ?, updated_at = ?, dispatch_started_at = ?
                WHERE schedule_id = ? AND status = ?
                """,
                (
                    ScoutScheduleStatus.RUNNING.value,
                    _iso(timestamp),
                    _iso(timestamp),
                    str(schedule_id),
                    ScoutScheduleStatus.PENDING.value,
                ),
            )
            changed = cursor.rowcount == 1
        return self.get(schedule_id) if changed else None

    def complete_success(
        self,
        schedule_id: UUID | str,
        scout_run: ScoutRunSuccess,
        *,
        now: datetime | None = None,
    ) -> ScoutScheduleRecord:
        return self._terminal_transition(
            schedule_id,
            expected=ScoutScheduleStatus.RUNNING,
            target=ScoutScheduleStatus.SUCCEEDED,
            scout_run=scout_run,
            now=now,
        )

    def complete_failure(
        self,
        schedule_id: UUID | str,
        *,
        error_code: str,
        error_message: str,
        scout_run: ScoutRunFailure | None = None,
        expected: ScoutScheduleStatus = ScoutScheduleStatus.RUNNING,
        now: datetime | None = None,
    ) -> ScoutScheduleRecord:
        return self._terminal_transition(
            schedule_id,
            expected=expected,
            target=ScoutScheduleStatus.FAILED,
            error_code=error_code,
            error_message=error_message,
            scout_run=scout_run,
            now=now,
        )

    def complete_recurring_success(
        self,
        schedule_id: UUID | str,
        scout_run: ScoutRunSuccess,
        *,
        next_trigger_at: datetime,
        now: datetime | None = None,
    ) -> ScoutScheduleRecord:
        return self._complete_recurring_execution(
            schedule_id,
            next_trigger_at=next_trigger_at,
            scout_run=scout_run,
            now=now,
        )

    def complete_recurring_failure(
        self,
        schedule_id: UUID | str,
        *,
        next_trigger_at: datetime,
        error_code: str,
        error_message: str,
        scout_run: ScoutRunFailure | None = None,
        now: datetime | None = None,
    ) -> ScoutScheduleRecord:
        return self._complete_recurring_execution(
            schedule_id,
            next_trigger_at=next_trigger_at,
            error_code=error_code,
            error_message=error_message,
            scout_run=scout_run,
            now=now,
        )

    def cancel_pending(
        self, schedule_id: UUID | str, *, now: datetime | None = None
    ) -> ScoutScheduleRecord:
        timestamp = _utc_now(now)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE scout_schedules
                SET status = ?, updated_at = ?, terminal_at = ?
                WHERE schedule_id = ? AND status = ?
                """,
                (
                    ScoutScheduleStatus.CANCELLED.value,
                    _iso(timestamp),
                    _iso(timestamp),
                    str(schedule_id),
                    ScoutScheduleStatus.PENDING.value,
                ),
            )
            self._raise_for_failed_transition(
                connection,
                cursor,
                schedule_id,
                ScoutScheduleStatus.CANCELLED,
            )
        return self.get(schedule_id)

    def mark_missed(
        self,
        schedule_id: UUID | str,
        *,
        message: str = "The scheduled time exceeded the configured misfire grace period.",
        now: datetime | None = None,
    ) -> ScoutScheduleRecord:
        return self._terminal_transition(
            schedule_id,
            expected=ScoutScheduleStatus.PENDING,
            target=ScoutScheduleStatus.MISSED,
            error_code="schedule_missed",
            error_message=message,
            now=now,
        )

    def advance_recurring_after_miss(
        self,
        schedule_id: UUID | str,
        *,
        next_trigger_at: datetime,
        message: str = "A recurring occurrence exceeded the misfire grace period.",
        now: datetime | None = None,
    ) -> ScoutScheduleRecord:
        return self._pending_recurring_transition(
            schedule_id,
            expected=ScoutScheduleStatus.PENDING,
            next_trigger_at=next_trigger_at,
            error_code="schedule_missed",
            error_message=message,
            now=now,
        )

    def advance_recurring_after_recovery(
        self,
        schedule_id: UUID | str,
        *,
        next_trigger_at: datetime,
        now: datetime | None = None,
    ) -> ScoutScheduleRecord:
        record = self.get(schedule_id)
        return self._pending_recurring_transition(
            schedule_id,
            expected=ScoutScheduleStatus.PENDING,
            next_trigger_at=next_trigger_at,
            error_code=record.error_code,
            error_message=record.error_message,
            now=now,
        )

    def recover_stale_running(
        self, *, now: datetime | None = None
    ) -> list[ScoutScheduleRecord]:
        stale = self.list_with_statuses([ScoutScheduleStatus.RUNNING])
        recovered: list[ScoutScheduleRecord] = []
        for record in stale:
            try:
                message = (
                    "The scheduler restarted while this dispatch was running; "
                    "the Scout run was not retried to avoid duplicate execution."
                )
                if record.recurrence is ScoutScheduleRecurrence.ONCE:
                    recovered.append(
                        self.complete_failure(
                            record.schedule_id,
                            error_code="stale_running_recovery",
                            error_message=message,
                            now=now,
                        )
                    )
                else:
                    recovered.append(
                        self._pending_recurring_transition(
                            record.schedule_id,
                            expected=ScoutScheduleStatus.RUNNING,
                            next_trigger_at=record.trigger_at,
                            error_code="stale_running_recovery",
                            error_message=message,
                            now=now,
                        )
                    )
            except ScheduleTransitionError:
                continue
        return recovered

    def _complete_recurring_execution(
        self,
        schedule_id: UUID | str,
        *,
        next_trigger_at: datetime,
        error_code: str | None = None,
        error_message: str | None = None,
        scout_run: ScoutRunSuccess | ScoutRunFailure | None = None,
        now: datetime | None = None,
    ) -> ScoutScheduleRecord:
        return self._pending_recurring_transition(
            schedule_id,
            expected=ScoutScheduleStatus.RUNNING,
            next_trigger_at=next_trigger_at,
            error_code=error_code,
            error_message=error_message,
            scout_run=scout_run,
            now=now,
        )

    def _pending_recurring_transition(
        self,
        schedule_id: UUID | str,
        *,
        expected: ScoutScheduleStatus,
        next_trigger_at: datetime,
        error_code: str | None,
        error_message: str | None,
        scout_run: ScoutRunSuccess | ScoutRunFailure | None = None,
        now: datetime | None = None,
    ) -> ScoutScheduleRecord:
        timestamp = _utc_now(now)
        trigger_at = _utc_now(next_trigger_at)
        run_at = trigger_at.astimezone(SEOUL_TIMEZONE).replace(tzinfo=None)
        scout_json = (
            scout_run.model_dump_json(exclude_none=True)
            if scout_run is not None
            else None
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE scout_schedules
                SET status = ?, run_at_local = ?, trigger_at_utc = ?,
                    updated_at = ?, terminal_at = ?, error_code = ?,
                    error_message = ?, scout_run_json = COALESCE(?, scout_run_json)
                WHERE schedule_id = ? AND status = ? AND recurrence != 'once'
                """,
                (
                    ScoutScheduleStatus.PENDING.value,
                    run_at.isoformat(),
                    _iso(trigger_at),
                    _iso(timestamp),
                    _iso(timestamp),
                    error_code,
                    error_message,
                    scout_json,
                    str(schedule_id),
                    expected.value,
                ),
            )
            self._raise_for_failed_transition(
                connection,
                cursor,
                schedule_id,
                ScoutScheduleStatus.PENDING,
            )
        return self.get(schedule_id)

    def _terminal_transition(
        self,
        schedule_id: UUID | str,
        *,
        expected: ScoutScheduleStatus,
        target: ScoutScheduleStatus,
        error_code: str | None = None,
        error_message: str | None = None,
        scout_run: ScoutRunSuccess | ScoutRunFailure | None = None,
        now: datetime | None = None,
    ) -> ScoutScheduleRecord:
        timestamp = _utc_now(now)
        scout_json = (
            scout_run.model_dump_json(exclude_none=True)
            if scout_run is not None
            else None
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE scout_schedules
                SET status = ?, updated_at = ?, terminal_at = ?, error_code = ?,
                    error_message = ?, scout_run_json = ?
                WHERE schedule_id = ? AND status = ?
                """,
                (
                    target.value,
                    _iso(timestamp),
                    _iso(timestamp),
                    error_code,
                    error_message,
                    scout_json,
                    str(schedule_id),
                    expected.value,
                ),
            )
            if cursor.rowcount != 1:
                self._raise_for_failed_transition(
                    connection,
                    cursor,
                    schedule_id,
                    target,
                )
        return self.get(schedule_id)

    @staticmethod
    def _raise_for_failed_transition(
        connection: sqlite3.Connection,
        cursor: sqlite3.Cursor,
        schedule_id: UUID | str,
        target: ScoutScheduleStatus,
    ) -> None:
        if cursor.rowcount == 1:
            return
        existing = connection.execute(
            "SELECT status FROM scout_schedules WHERE schedule_id = ?",
            (str(schedule_id),),
        ).fetchone()
        if existing is None:
            raise ScheduleNotFoundError(str(schedule_id))
        raise ScheduleTransitionError(
            f"Schedule cannot transition from {existing['status']} to {target.value}."
        )


def _row_to_record(row: sqlite3.Row) -> ScoutScheduleRecord:
    scout_run = None
    if row["scout_run_json"]:
        scout_run = TERMINAL_ADAPTER.validate_json(row["scout_run_json"])
    return ScoutScheduleRecord(
        schedule_id=row["schedule_id"],
        topic=row["topic"],
        keywords=json.loads(row["keywords_json"]),
        additional_instructions=row["additional_instructions"],
        recurrence=row["recurrence"],
        run_at=datetime.fromisoformat(row["run_at_local"]),
        schedule_time=(
            datetime.strptime(row["schedule_time_local"], "%H:%M:%S").time()
            if row["schedule_time_local"]
            else None
        ),
        day_of_week=row["day_of_week"],
        day_of_month=row["day_of_month"],
        timezone=row["timezone"],
        trigger_at=datetime.fromisoformat(row["trigger_at_utc"]),
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        dispatch_started_at=(
            datetime.fromisoformat(row["dispatch_started_at"])
            if row["dispatch_started_at"]
            else None
        ),
        terminal_at=(
            datetime.fromisoformat(row["terminal_at"]) if row["terminal_at"] else None
        ),
        error_code=row["error_code"],
        error_message=row["error_message"],
        scout_run=scout_run,
    )


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _utc_now(value: datetime | None = None) -> datetime:
    timestamp = value or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("repository timestamps must be timezone-aware")
    return timestamp.astimezone(UTC)

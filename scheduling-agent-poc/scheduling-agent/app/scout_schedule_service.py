from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from uuid import UUID

from apscheduler.events import EVENT_JOB_MISSED, JobExecutionEvent
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from app.scout_api_client import (
    ScoutApiCallError,
    ScoutApiClient,
    ScoutRunFailedResponse,
)
from app.scout_schedule_models import (
    SEOUL_TIMEZONE,
    ScoutScheduleCreateRequest,
    ScoutScheduleListResponse,
    ScoutScheduleRecord,
    ScoutScheduleRecurrence,
    ScoutScheduleStatus,
)
from app.scout_schedule_repository import (
    ScheduleNotFoundError,
    ScheduleTransitionError,
    ScoutScheduleRepository,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "var" / "scout_schedules.sqlite3"

_ACTIVE_SERVICE: ScoutScheduleService | None = None
_ACTIVE_SERVICE_LOCK = threading.Lock()


@dataclass(frozen=True)
class ScoutScheduleSettings:
    scout_api_base_url: str = "http://127.0.0.1:8091"
    database_path: Path = DEFAULT_DATABASE_PATH
    scout_timeout_seconds: float = 180.0
    concurrency_limit: int = 1
    misfire_grace_seconds: int = 300

    @classmethod
    def from_env(cls) -> ScoutScheduleSettings:
        settings = cls(
            scout_api_base_url=os.getenv("SCOUT_API_BASE_URL", "http://127.0.0.1:8091"),
            database_path=Path(
                os.getenv("SCOUT_SCHEDULE_DB_PATH", str(DEFAULT_DATABASE_PATH))
            ),
            scout_timeout_seconds=float(os.getenv("SCOUT_API_TIMEOUT_SECONDS", "180")),
            concurrency_limit=int(os.getenv("SCOUT_SCHEDULER_CONCURRENCY", "1")),
            misfire_grace_seconds=int(
                os.getenv("SCOUT_SCHEDULER_MISFIRE_GRACE_SECONDS", "300")
            ),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.scout_api_base_url.strip():
            raise ValueError("SCOUT_API_BASE_URL must not be blank")
        if self.scout_timeout_seconds <= 0:
            raise ValueError("SCOUT_API_TIMEOUT_SECONDS must be greater than zero")
        if self.concurrency_limit < 1:
            raise ValueError("SCOUT_SCHEDULER_CONCURRENCY must be at least one")
        if self.misfire_grace_seconds < 1:
            raise ValueError(
                "SCOUT_SCHEDULER_MISFIRE_GRACE_SECONDS must be at least one"
            )


class ScheduleRegistrationError(RuntimeError):
    pass


class ScoutScheduleService:
    def __init__(
        self,
        settings: ScoutScheduleSettings,
        *,
        repository: ScoutScheduleRepository | None = None,
        scout_client: ScoutApiClient | None = None,
        scheduler: BackgroundScheduler | None = None,
    ) -> None:
        settings.validate()
        self.settings = settings
        self.repository = repository or ScoutScheduleRepository(settings.database_path)
        self.scout_client = scout_client or ScoutApiClient(
            settings.scout_api_base_url,
            settings.scout_timeout_seconds,
        )
        self.scheduler = scheduler or _build_scheduler(settings)
        self.scheduler.add_listener(self._handle_missed_job, EVENT_JOB_MISSED)
        self._started = False

    @property
    def is_running(self) -> bool:
        return self._started and self.scheduler.running

    def start(self) -> None:
        global _ACTIVE_SERVICE

        if self._started:
            return
        with _ACTIVE_SERVICE_LOCK:
            if _ACTIVE_SERVICE is not None and _ACTIVE_SERVICE is not self:
                raise RuntimeError(
                    "Only one Scout scheduler process owner is supported."
                )
            _ACTIVE_SERVICE = self

        scheduler_started = False
        try:
            recovery_time = datetime.now(UTC)
            recovered = self.repository.recover_stale_running(now=recovery_time)
            for record in recovered:
                if record.recurrence is not ScoutScheduleRecurrence.ONCE:
                    self.repository.advance_recurring_after_recovery(
                        record.schedule_id,
                        next_trigger_at=self._next_recurring_trigger(
                            record,
                            now=recovery_time,
                        ),
                        now=recovery_time,
                    )
            self.scheduler.start(paused=True)
            scheduler_started = True
            self._reconcile_pending_jobs()
            self.scheduler.resume()
            self._started = True
        except Exception:
            if scheduler_started and self.scheduler.running:
                self.scheduler.shutdown(wait=True)
            with _ACTIVE_SERVICE_LOCK:
                if _ACTIVE_SERVICE is self:
                    _ACTIVE_SERVICE = None
            raise

    def shutdown(self) -> None:
        global _ACTIVE_SERVICE

        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=True)
        finally:
            self._started = False
            with _ACTIVE_SERVICE_LOCK:
                if _ACTIVE_SERVICE is self:
                    _ACTIVE_SERVICE = None
            self.scout_client.close()

    def create_schedule(
        self, request: ScoutScheduleCreateRequest
    ) -> ScoutScheduleRecord:
        trigger_at = None
        if request.recurrence is not ScoutScheduleRecurrence.ONCE:
            trigger = _build_recurring_trigger(
                request.recurrence,
                schedule_time=request.schedule_time,
                day_of_week=(
                    request.day_of_week.value
                    if request.day_of_week is not None
                    else None
                ),
                day_of_month=request.day_of_month,
            )
            trigger_at = trigger.get_next_fire_time(None, datetime.now(UTC))
            if trigger_at is None:
                raise ScheduleRegistrationError(
                    "The recurring schedule has no future occurrence."
                )
        record = self.repository.create(request, trigger_at=trigger_at)
        try:
            self._register_job(record)
        except Exception:
            self.repository.complete_failure(
                record.schedule_id,
                expected=ScoutScheduleStatus.PENDING,
                error_code="schedule_registration_failed",
                error_message="The schedule could not be registered.",
            )
            raise ScheduleRegistrationError(
                "The schedule could not be registered."
            ) from None
        return self.repository.get(record.schedule_id)

    def list_schedules(self) -> ScoutScheduleListResponse:
        return ScoutScheduleListResponse(schedules=self.repository.list())

    def cancel_schedule(self, schedule_id: UUID) -> ScoutScheduleRecord:
        record = self.repository.cancel_pending(schedule_id)
        job = self.scheduler.get_job(str(schedule_id))
        if job is not None:
            self.scheduler.remove_job(str(schedule_id))
        return record

    def execute_schedule(self, schedule_id: UUID | str) -> None:
        claimed = self.repository.claim_pending(schedule_id)
        if claimed is None:
            return

        next_trigger_at = (
            self._next_recurring_trigger(claimed)
            if claimed.recurrence is not ScoutScheduleRecurrence.ONCE
            else None
        )

        try:
            scout_run = self.scout_client.run_scout(
                claimed.topic,
                claimed.keywords,
                claimed.additional_instructions,
            )
        except ScoutRunFailedResponse as exc:
            if next_trigger_at is None:
                self.repository.complete_failure(
                    schedule_id,
                    error_code=exc.code,
                    error_message=exc.safe_message,
                    scout_run=exc.run,
                )
            else:
                self.repository.complete_recurring_failure(
                    schedule_id,
                    next_trigger_at=next_trigger_at,
                    error_code=exc.code,
                    error_message=exc.safe_message,
                    scout_run=exc.run,
                )
        except ScoutApiCallError as exc:
            if next_trigger_at is None:
                self.repository.complete_failure(
                    schedule_id,
                    error_code=exc.code,
                    error_message=exc.safe_message,
                )
            else:
                self.repository.complete_recurring_failure(
                    schedule_id,
                    next_trigger_at=next_trigger_at,
                    error_code=exc.code,
                    error_message=exc.safe_message,
                )
        except Exception:
            if next_trigger_at is None:
                self.repository.complete_failure(
                    schedule_id,
                    error_code="schedule_callback_failed",
                    error_message="The scheduled Scout callback failed.",
                )
            else:
                self.repository.complete_recurring_failure(
                    schedule_id,
                    next_trigger_at=next_trigger_at,
                    error_code="schedule_callback_failed",
                    error_message="The scheduled Scout callback failed.",
                )
        else:
            if next_trigger_at is None:
                self.repository.complete_success(schedule_id, scout_run)
            else:
                self.repository.complete_recurring_success(
                    schedule_id,
                    scout_run,
                    next_trigger_at=next_trigger_at,
                )

    def _register_job(self, record: ScoutScheduleRecord) -> None:
        job_options: dict[str, object] = {}
        if record.recurrence is not ScoutScheduleRecurrence.ONCE:
            job_options["next_run_time"] = record.trigger_at
        self.scheduler.add_job(
            _execute_persisted_scout_schedule,
            trigger=_build_schedule_trigger(record),
            args=[str(record.schedule_id)],
            id=str(record.schedule_id),
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=self.settings.misfire_grace_seconds,
            **job_options,
        )

    def _next_recurring_trigger(
        self,
        record: ScoutScheduleRecord,
        *,
        now: datetime | None = None,
    ) -> datetime:
        if record.recurrence is ScoutScheduleRecurrence.ONCE:
            raise ValueError("a one-time schedule has no recurring trigger")
        trigger = _build_schedule_trigger(record)
        after = max(now or datetime.now(UTC), record.trigger_at) + timedelta(
            microseconds=1
        )
        next_trigger = trigger.get_next_fire_time(None, after)
        if next_trigger is None:
            raise RuntimeError("The recurring schedule has no future occurrence.")
        return next_trigger.astimezone(UTC)

    def _reconcile_pending_jobs(self, *, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        grace_boundary = now - timedelta(seconds=self.settings.misfire_grace_seconds)
        pending = self.repository.list_with_statuses([ScoutScheduleStatus.PENDING])
        pending_ids: set[str] = set()

        for record in pending:
            schedule_id = str(record.schedule_id)
            if record.trigger_at < grace_boundary:
                if record.recurrence is ScoutScheduleRecurrence.ONCE:
                    self.repository.mark_missed(record.schedule_id, now=now)
                else:
                    record = self.repository.advance_recurring_after_miss(
                        record.schedule_id,
                        next_trigger_at=self._next_recurring_trigger(
                            record,
                            now=now,
                        ),
                        now=now,
                    )
                existing = self.scheduler.get_job(schedule_id)
                if existing is not None:
                    self.scheduler.remove_job(schedule_id)
                if record.recurrence is ScoutScheduleRecurrence.ONCE:
                    continue
            pending_ids.add(schedule_id)
            self._register_job(record)

        for job in self.scheduler.get_jobs():
            if job.id not in pending_ids:
                self.scheduler.remove_job(job.id)

    def _handle_missed_job(self, event: JobExecutionEvent) -> None:
        try:
            record = self.repository.get(event.job_id)
            if record.recurrence is ScoutScheduleRecurrence.ONCE:
                self.repository.mark_missed(event.job_id)
            else:
                self.repository.advance_recurring_after_miss(
                    event.job_id,
                    next_trigger_at=self._next_recurring_trigger(record),
                )
        except (
            ScheduleNotFoundError,
            ScheduleTransitionError,
            RuntimeError,
            ValueError,
        ):
            return


def build_scout_schedule_service() -> ScoutScheduleService:
    return ScoutScheduleService(ScoutScheduleSettings.from_env())


def _build_scheduler(settings: ScoutScheduleSettings) -> BackgroundScheduler:
    database_path = settings.database_path.expanduser().resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return BackgroundScheduler(
        jobstores={
            "default": SQLAlchemyJobStore(url=f"sqlite:///{database_path}"),
        },
        executors={
            "default": ThreadPoolExecutor(max_workers=settings.concurrency_limit),
        },
        timezone=UTC,
    )


def _build_schedule_trigger(record: ScoutScheduleRecord) -> DateTrigger | CronTrigger:
    if record.recurrence is ScoutScheduleRecurrence.ONCE:
        return DateTrigger(run_date=record.trigger_at)
    return _build_recurring_trigger(
        record.recurrence,
        schedule_time=record.schedule_time,
        day_of_week=(
            record.day_of_week.value if record.day_of_week is not None else None
        ),
        day_of_month=record.day_of_month,
    )


def _build_recurring_trigger(
    recurrence: ScoutScheduleRecurrence,
    *,
    schedule_time: time | None,
    day_of_week: str | None,
    day_of_month: int | None,
) -> CronTrigger:
    if schedule_time is None:
        raise ValueError("a recurring schedule requires schedule_time")
    hour = schedule_time.hour
    minute = schedule_time.minute
    second = schedule_time.second
    fields: dict[str, object] = {
        "hour": hour,
        "minute": minute,
        "second": second,
        "timezone": SEOUL_TIMEZONE,
    }
    if recurrence is ScoutScheduleRecurrence.WEEKLY:
        if day_of_week is None:
            raise ValueError("a weekly schedule requires day_of_week")
        fields["day_of_week"] = day_of_week[:3]
    elif recurrence is ScoutScheduleRecurrence.MONTHLY:
        if day_of_month is None:
            raise ValueError("a monthly schedule requires day_of_month")
        fields["day"] = day_of_month
    elif recurrence is not ScoutScheduleRecurrence.DAILY:
        raise ValueError("unsupported recurring schedule")
    return CronTrigger(**fields)


def _execute_persisted_scout_schedule(schedule_id: str) -> None:
    with _ACTIVE_SERVICE_LOCK:
        service = _ACTIVE_SERVICE
    if service is None:
        raise RuntimeError("Scout scheduling service is not active.")
    service.execute_schedule(schedule_id)

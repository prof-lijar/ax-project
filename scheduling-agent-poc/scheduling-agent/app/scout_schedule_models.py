from __future__ import annotations

import re
from datetime import UTC, datetime, time
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

SEOUL_TIMEZONE_NAME = "Asia/Seoul"
SEOUL_TIMEZONE = ZoneInfo(SEOUL_TIMEZONE_NAME)
LOCAL_DATETIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?$"
)
LOCAL_TIME_PATTERN = re.compile(r"^\d{2}:\d{2}(?::\d{2})?$")


class ScoutScheduleStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    MISSED = "missed"


class ScoutScheduleRecurrence(StrEnum):
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ScoutScheduleDayOfWeek(StrEnum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


class ScoutScheduleCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=3, max_length=500)
    keywords: list[str] = Field(default_factory=list, max_length=10)
    additional_instructions: str | None = Field(default=None, max_length=2_000)
    recurrence: ScoutScheduleRecurrence = ScoutScheduleRecurrence.ONCE
    run_at: datetime | None = None
    schedule_time: time | None = None
    day_of_week: ScoutScheduleDayOfWeek | None = None
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    timezone: Literal["Asia/Seoul"]

    @field_validator("topic")
    @classmethod
    def normalize_topic(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("topic must contain at least three characters")
        return value

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_value in values:
            value = raw_value.strip()
            if not value:
                raise ValueError("keywords must not be blank")
            if len(value) > 100:
                raise ValueError("each keyword must contain at most 100 characters")
            key = value.casefold()
            if key not in seen:
                seen.add(key)
                normalized.append(value)
        return normalized

    @field_validator("additional_instructions", mode="before")
    @classmethod
    def normalize_additional_instructions(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @field_validator("run_at", mode="before")
    @classmethod
    def validate_local_datetime_shape(cls, value: object) -> object:
        if value is None:
            return value
        if not isinstance(value, str) or not LOCAL_DATETIME_PATTERN.fullmatch(value):
            raise ValueError(
                "run_at must be an ISO local datetime without a timezone offset"
            )
        return value

    @field_validator("run_at")
    @classmethod
    def validate_future_seoul_time(cls, value: datetime) -> datetime:
        if value is None:
            return value
        if value.tzinfo is not None or value.utcoffset() is not None:
            raise ValueError("run_at must be a timezone-naive local datetime")
        run_at_kst = value.replace(tzinfo=SEOUL_TIMEZONE)
        if run_at_kst <= datetime.now(SEOUL_TIMEZONE):
            raise ValueError("run_at must be in the future")
        return value

    @field_validator("schedule_time", mode="before")
    @classmethod
    def validate_local_time_shape(cls, value: object) -> object:
        if value is None:
            return value
        if not isinstance(value, str) or not LOCAL_TIME_PATTERN.fullmatch(value):
            raise ValueError("schedule_time must be HH:MM or HH:MM:SS")
        return value

    @field_validator("schedule_time")
    @classmethod
    def validate_local_time(cls, value: time | None) -> time | None:
        if value is not None and (
            value.tzinfo is not None or value.utcoffset() is not None
        ):
            raise ValueError("schedule_time must be timezone-naive")
        return value

    @model_validator(mode="after")
    def validate_recurrence_fields(self) -> ScoutScheduleCreateRequest:
        if self.recurrence is ScoutScheduleRecurrence.ONCE:
            if self.run_at is None:
                raise ValueError("run_at is required for a one-time schedule")
            if any(
                value is not None
                for value in (self.schedule_time, self.day_of_week, self.day_of_month)
            ):
                raise ValueError(
                    "recurrence fields are not accepted for a one-time schedule"
                )
            return self

        if self.run_at is not None:
            raise ValueError("run_at is accepted only for a one-time schedule")
        if self.schedule_time is None:
            raise ValueError("schedule_time is required for a recurring schedule")
        if self.recurrence is ScoutScheduleRecurrence.DAILY:
            if self.day_of_week is not None or self.day_of_month is not None:
                raise ValueError("daily schedules accept only schedule_time")
        elif self.recurrence is ScoutScheduleRecurrence.WEEKLY:
            if self.day_of_week is None or self.day_of_month is not None:
                raise ValueError("weekly schedules require day_of_week")
        elif self.day_of_month is None or self.day_of_week is not None:
            raise ValueError("monthly schedules require day_of_month")
        return self

    @property
    def trigger_at_utc(self) -> datetime:
        if self.run_at is None:
            raise ValueError("recurring schedules do not have a fixed trigger_at")
        return self.run_at.replace(tzinfo=SEOUL_TIMEZONE).astimezone(UTC)


class ScoutRunSuccess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: Literal["success"]
    started_at: datetime
    completed_at: datetime
    duration_seconds: float = Field(ge=0)
    source_count: int = Field(ge=1)
    report: str = Field(min_length=1)
    sources: list[str]
    report_artifact: str
    log_artifact: str

    @model_validator(mode="after")
    def validate_terminal_metadata(self) -> ScoutRunSuccess:
        _validate_aware_timestamps(self.started_at, self.completed_at)
        if self.source_count != len(self.sources):
            raise ValueError("source_count must equal the number of sources")
        return self


class ScoutRunFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: Literal["failed"]
    started_at: datetime
    completed_at: datetime
    duration_seconds: float = Field(ge=0)
    source_count: Literal[0] = 0
    log_artifact: str

    @model_validator(mode="after")
    def validate_terminal_metadata(self) -> ScoutRunFailure:
        _validate_aware_timestamps(self.started_at, self.completed_at)
        return self


ScoutRunTerminal = Annotated[
    ScoutRunSuccess | ScoutRunFailure,
    Field(discriminator="status"),
]


class ScoutScheduleRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule_id: UUID
    topic: str
    keywords: list[str]
    additional_instructions: str | None = None
    recurrence: ScoutScheduleRecurrence
    run_at: datetime
    schedule_time: time | None = None
    day_of_week: ScoutScheduleDayOfWeek | None = None
    day_of_month: int | None = None
    timezone: Literal["Asia/Seoul"]
    trigger_at: datetime
    status: ScoutScheduleStatus
    created_at: datetime
    updated_at: datetime
    dispatch_started_at: datetime | None = None
    terminal_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    scout_run: ScoutRunTerminal | None = None


class ScoutScheduleListResponse(BaseModel):
    schedules: list[ScoutScheduleRecord]


def _validate_aware_timestamps(started_at: datetime, completed_at: datetime) -> None:
    if started_at.tzinfo is None or started_at.utcoffset() is None:
        raise ValueError("started_at must be timezone-aware")
    if completed_at.tzinfo is None or completed_at.utcoffset() is None:
        raise ValueError("completed_at must be timezone-aware")
    if completed_at < started_at:
        raise ValueError("completed_at must not be before started_at")

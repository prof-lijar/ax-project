"""Workflow-local records that never cross the public graph boundary."""

import re
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WorkflowModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DailyActivity(WorkflowModel):
    activity_date: date
    assigned_tasks: int = Field(ge=0)
    completed_tasks: int = Field(ge=0)
    focus_minutes: int = Field(ge=0)
    blockers_opened: int = Field(ge=0)
    blockers_resolved: int = Field(ge=0)

    @property
    def is_active(self) -> bool:
        return any(
            (
                self.assigned_tasks,
                self.completed_tasks,
                self.focus_minutes,
                self.blockers_opened,
                self.blockers_resolved,
            )
        )


class UserActivityWindow(WorkflowModel):
    user_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=256)
    records: list[DailyActivity] = Field(max_length=14)

    @model_validator(mode="after")
    def validate_unique_dates(self) -> "UserActivityWindow":
        dates = [record.activity_date for record in self.records]
        if len(dates) != len(set(dates)):
            raise ValueError("activity records must have unique dates per user")
        return self


class KoreanNarrative(WorkflowModel):
    """Small, validated model output; calculations never enter this contract."""

    summary: str = Field(min_length=1, max_length=600)
    suggestions: list[str] = Field(min_length=2, max_length=3)

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        return _validate_korean_narrative_text(value)

    @field_validator("suggestions")
    @classmethod
    def validate_suggestions(cls, values: list[str]) -> list[str]:
        normalized = [_validate_korean_narrative_text(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("suggestions must be unique")
        return normalized


def _validate_korean_narrative_text(value: str) -> str:
    if not re.search(r"[가-힣]", value):
        raise ValueError("narrative text must contain Korean")
    if re.search(r"\d", value):
        raise ValueError("narrative text must not contain digits")
    return value

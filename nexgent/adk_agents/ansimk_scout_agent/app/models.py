from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ScoutRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=3, max_length=500)
    keywords: list[str] = Field(default_factory=list, max_length=10)
    additional_instructions: str | None = Field(default=None, max_length=2_000)

    @field_validator("topic")
    @classmethod
    def normalize_topic(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("topic must contain at least three non-whitespace characters")
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


class ScoutRunResponse(BaseModel):
    run_id: str
    status: Literal["success"]
    started_at: datetime
    completed_at: datetime
    duration_seconds: float = Field(ge=0)
    source_count: int = Field(ge=1)
    report: str
    sources: list[str]
    report_artifact: str
    log_artifact: str

    @model_validator(mode="after")
    def validate_terminal_metadata(self) -> ScoutRunResponse:
        _validate_timestamps(self.started_at, self.completed_at)
        if self.source_count != len(self.sources):
            raise ValueError("source_count must equal the number of sources")
        return self


class ScoutRunFailure(BaseModel):
    run_id: str
    status: Literal["failed"]
    started_at: datetime
    completed_at: datetime
    duration_seconds: float = Field(ge=0)
    source_count: Literal[0] = 0
    log_artifact: str

    @model_validator(mode="after")
    def validate_terminal_metadata(self) -> ScoutRunFailure:
        _validate_timestamps(self.started_at, self.completed_at)
        return self


class ScoutRunErrorResponse(BaseModel):
    detail: Literal["Scout run failed."]
    run: ScoutRunFailure


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""


class FetchedPage(BaseModel):
    url: str
    title: str | None = None
    text: str
    content_type: str
    truncated: bool
    content_is_untrusted: Literal[True] = True


def _validate_timestamps(started_at: datetime, completed_at: datetime) -> None:
    if started_at.tzinfo is None or started_at.utcoffset() is None:
        raise ValueError("started_at must be timezone-aware")
    if completed_at.tzinfo is None or completed_at.utcoffset() is None:
        raise ValueError("completed_at must be timezone-aware")
    if completed_at < started_at:
        raise ValueError("completed_at must not be before started_at")

"""Workflow-local records that never cross the public graph boundary."""

import re
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WorkflowModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WardDangerDay(WorkflowModel):
    ward_id: int = Field(ge=1)
    danger_date: date
    first_detected_at: datetime


class WardRiskWindow(WorkflowModel):
    ward_id: int = Field(ge=1)
    display_name: str = Field(min_length=1, max_length=256)
    records: list[WardDangerDay] = Field(min_length=1, max_length=14)

    @model_validator(mode="after")
    def validate_records(self) -> "WardRiskWindow":
        dates = [record.danger_date for record in self.records]
        if len(dates) != len(set(dates)):
            raise ValueError("danger records must have unique dates per ward")
        if any(record.ward_id != self.ward_id for record in self.records):
            raise ValueError("danger records must match their ward window")
        return self


class WardRiskSelection(WorkflowModel):
    windows: list[WardRiskWindow] = Field(min_length=1, max_length=25)
    selection_truncated: bool


class McpRowsResult(WorkflowModel):
    """Bounded page returned by the MCP structured query tool."""

    schema_name: str = Field(min_length=1, max_length=128)
    table_name: str = Field(min_length=1, max_length=128)
    columns: list[str] = Field(min_length=1, max_length=32)
    rows: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    row_count: int = Field(ge=0, le=100)
    truncated: bool
    offset: int = Field(ge=0)
    duration_ms: float = Field(ge=0)
    warnings: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_page(self) -> "McpRowsResult":
        if self.row_count != len(self.rows):
            raise ValueError("MCP row_count must match returned rows")
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

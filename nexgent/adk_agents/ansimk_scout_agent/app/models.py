from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ScoutRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=3, max_length=500)
    keywords: list[str] = Field(default_factory=list, max_length=10)

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


class ScoutRunResponse(BaseModel):
    run_id: str
    status: Literal["success"]
    report: str
    sources: list[str]
    report_artifact: str
    log_artifact: str


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

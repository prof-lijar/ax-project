from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SearchPlan(BaseModel):
    """Validated, URL-free queries produced by the planning LLM stage."""

    model_config = ConfigDict(extra="forbid")

    queries: list[str] = Field(min_length=1, max_length=3)

    @field_validator("queries")
    @classmethod
    def normalize_queries(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_value in values:
            value = " ".join(raw_value.split())
            if not value:
                raise ValueError("search queries must not be blank")
            if len(value) > 160:
                raise ValueError("search queries must contain at most 160 characters")
            lowered = value.casefold()
            if "http://" in lowered or "https://" in lowered or "www." in lowered:
                raise ValueError("search plans must contain queries, not URLs")
            if lowered not in seen:
                seen.add(lowered)
                normalized.append(value)
        if not normalized:
            raise ValueError("search plan must contain at least one unique query")
        return normalized


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

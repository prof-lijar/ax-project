"""Workflow-local qualitative facts passed to the reporter agent."""

from pydantic import BaseModel, ConfigDict, Field


class FactPackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    coverage: str = Field(pattern=r"^(complete|incomplete|absent)$")
    facts: list[str] = Field(min_length=1, max_length=6)
    allowed_topics: list[str] = Field(min_length=1, max_length=6)
    suggested_actions: list[str] = Field(default_factory=list, max_length=3)

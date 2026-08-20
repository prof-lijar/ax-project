"""Workflow-local qualitative facts passed to the reporter agent."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FactPackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    coverage: str = Field(pattern=r"^(complete|incomplete|absent)$")
    facts: list[str] = Field(min_length=1, max_length=6)
    allowed_topics: list[str] = Field(min_length=1, max_length=6)
    required_topics: list[str] = Field(default_factory=list, max_length=6)
    suggested_actions: list[str] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def validate_required_topics(self) -> "FactPackage":
        if not set(self.required_topics).issubset(self.allowed_topics):
            raise ValueError("required_topics must be included in allowed_topics")
        return self

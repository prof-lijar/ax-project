"""Workflow-local qualitative facts passed to the reporter agent."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SectionSource = Literal[
    "movement_count",
    "remote_control_count",
    "temperature",
    "humidity",
    "device_data",
]
SectionStatus = Literal["GOOD", "CAUTION", "RISK"]


class SectionAssessment(BaseModel):
    """Qualitative, Python-verified sensor interpretation supplied to the LLM."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: SectionSource
    status: SectionStatus
    finding: str = Field(min_length=1, max_length=180)


class GuardianActionCandidate(BaseModel):
    """Exact action candidate selected by deterministic product rules."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(min_length=1, max_length=64)
    status: Literal["GOOD", "CAUTION", "RISK"]
    condition: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=200)
    tag: str = Field(min_length=1, max_length=50)
    template_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=32,
        pattern=r"^[A-Z]+(?:_[A-Z]+)*_\d{2}$",
    )


class WeeklySummarySection(BaseModel):
    """One deterministic report-section result supplied to the summary LLM."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str = Field(min_length=1, max_length=32)
    description: str = Field(min_length=1, max_length=300)
    summary: str | None = Field(default=None, min_length=1, max_length=100)


class WeeklySummaryData(BaseModel):
    """Safe, report-facing weekly data used to author one free-form summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subscriber: str = Field(min_length=1, max_length=256)
    overall: WeeklySummarySection
    living_activity: WeeklySummarySection
    living_pattern: WeeklySummarySection
    indoor_environment: WeeklySummarySection
    device_status: WeeklySummarySection
    risk_management: WeeklySummarySection
    guardian_actions: list[str] = Field(default_factory=list, max_length=3)


class FactPackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    coverage: str = Field(pattern=r"^(complete|incomplete|absent)$")
    facts: list[str] = Field(min_length=1, max_length=10)
    allowed_topics: list[str] = Field(min_length=1, max_length=6)
    required_topics: list[str] = Field(default_factory=list, max_length=6)
    suggested_actions: list[str] = Field(default_factory=list, max_length=3)
    section_assessments: list[SectionAssessment] = Field(
        default_factory=list,
        max_length=5,
    )
    guardian_action_candidates: list[GuardianActionCandidate] = Field(
        default_factory=list,
        max_length=3,
    )
    weekly_report_data: WeeklySummaryData | None = None

    @model_validator(mode="after")
    def validate_required_topics(self) -> "FactPackage":
        if not set(self.required_topics).issubset(self.allowed_topics):
            raise ValueError("required_topics must be included in allowed_topics")
        return self

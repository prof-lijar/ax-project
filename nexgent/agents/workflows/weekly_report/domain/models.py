"""Workflow-local qualitative facts passed to the reporter agent."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SummaryMode = Literal["ALL_GOOD", "MIXED", "RISK", "LOW_DATA", "PARTIAL_DEVICE"]
DataQualityCode = Literal["VALID", "LOW_DATA", "PARTIAL_POWER", "PARTIAL_POSITION"]
SectionSource = Literal[
    "movement_count",
    "remote_control_count",
    "temperature",
    "humidity",
    "device_data",
]
SectionStatus = Literal["GOOD", "CAUTION", "RISK"]


class SummaryOutline(BaseModel):
    """Python-owned semantic outline for one weekly summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: SummaryMode
    valid_days: int = Field(ge=0, le=7)
    data_quality_code: DataQualityCode
    headline: str = Field(min_length=1, max_length=180)
    life: str | None = Field(default=None, min_length=1, max_length=300)
    environment: str | None = Field(default=None, min_length=1, max_length=300)
    safety: str | None = Field(default=None, min_length=1, max_length=300)
    close: str = Field(min_length=1, max_length=240)
    good_topic_list: list[str] = Field(default_factory=list, max_length=3)
    issue_topic_list: list[str] = Field(default_factory=list, max_length=3)
    available_item_list: list[str] = Field(default_factory=list, max_length=4)
    omitted_item_list: list[str] = Field(default_factory=list, max_length=4)


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
    analysis: str = Field(min_length=1, max_length=200)


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
    summary_outline: SummaryOutline | None = None

    @model_validator(mode="after")
    def validate_required_topics(self) -> "FactPackage":
        if not set(self.required_topics).issubset(self.allowed_topics):
            raise ValueError("required_topics must be included in allowed_topics")
        if self.summary_outline is not None:
            expected_facts = [
                self.summary_outline.headline,
                *(
                    block
                    for block in (
                        self.summary_outline.life,
                        self.summary_outline.environment,
                        self.summary_outline.safety,
                    )
                    if block is not None
                ),
            ]
            if self.facts != expected_facts:
                raise ValueError("facts must match summary_outline in semantic order")
        return self

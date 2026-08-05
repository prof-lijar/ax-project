"""Pydantic contracts crossing package, process, or persistence boundaries."""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    schema_version: str = Field(default=SCHEMA_VERSION, frozen=True)


class RunContext(ContractModel):
    """Identity and limits propagated through every graph execution."""

    tenant_id: str = Field(min_length=1, max_length=128)
    correlation_id: UUID = Field(default_factory=uuid4)
    thread_id: str | None = None
    run_id: UUID | None = None
    deadline: datetime | None = None
    attempt: int = Field(default=1, ge=1)


class TaskEnvelope(ContractModel):
    task_id: UUID = Field(default_factory=uuid4)
    objective: str = Field(min_length=1, max_length=20_000)
    context: dict[str, Any] = Field(default_factory=dict)
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    created_at: datetime = Field(default_factory=_utc_now)
    requested_by: str | None = None


class AgentInput(ContractModel):
    message: str = Field(min_length=1, max_length=100_000)
    context: dict[str, Any] = Field(default_factory=dict)


class AgentOutput(ContractModel):
    status: Literal["completed", "blocked", "failed"]
    message: str = Field(min_length=1)
    artifacts: list["ArtifactRef"] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class ArtifactRef(ContractModel):
    uri: str = Field(min_length=1, max_length=2_000)
    artifact_type: str = Field(min_length=1, max_length=128)
    checksum: str | None = None
    version: str | None = None


class ToolRequest(ContractModel):
    tool_name: str = Field(min_length=1, max_length=128)
    arguments: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=256)
    risk: Literal["read", "write", "destructive"] = "read"


class ToolResult(ContractModel):
    tool_name: str
    status: Literal["succeeded", "failed", "denied", "timed_out"]
    output: Any = None
    error_code: str | None = None
    retryable: bool = False


class Handoff(ContractModel):
    source_agent: str = Field(min_length=1, max_length=128)
    target_agent: str = Field(min_length=1, max_length=128)
    objective: str = Field(min_length=1, max_length=20_000)
    required_artifacts: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    stop_conditions: list[str] = Field(default_factory=list)


class EvaluationResult(ContractModel):
    criterion: str = Field(min_length=1, max_length=512)
    status: Literal["passed", "failed", "inconclusive"]
    severity: Literal["info", "warning", "error", "critical"] = "info"
    score: float | None = Field(default=None, ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    recommendation: str | None = None

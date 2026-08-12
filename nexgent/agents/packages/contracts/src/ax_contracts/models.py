"""Pydantic contracts crossing package, process, or persistence boundaries."""

import re
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


_DOMAIN_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


def _normalize_domain(value: str) -> str:
    domain = value.strip().lower().rstrip(".")
    if not domain or "://" in domain or "/" in domain or "@" in domain:
        raise ValueError("domains must be bare hostnames without a scheme or path")
    try:
        return str(ip_address(domain))
    except ValueError:
        pass
    try:
        domain = domain.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("domain is not a valid internationalized hostname") from exc
    if len(domain) > 253 or any(
        not _DOMAIN_LABEL.fullmatch(label) for label in domain.split(".")
    ):
        raise ValueError("domain is not a valid hostname")
    return domain


def _validate_http_url(value: str) -> str:
    normalized = value.strip()
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("url must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("url must not contain credentials")
    return normalized


class WebSearchInput(ContractModel):
    """Provider-neutral input for discovering public web sources."""

    query: str = Field(min_length=1, max_length=500)
    result_limit: int = Field(default=8, ge=1, le=20)
    language: str = Field(default="auto", min_length=2, max_length=16)
    time_range: Literal["day", "month", "year"] | None = None
    allowed_domains: list[str] | None = Field(default=None, max_length=100)
    blocked_domains: list[str] | None = Field(default=None, max_length=100)

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        normalized = value.strip()
        if normalized != "auto" and not re.fullmatch(
            r"[A-Za-z]{2,3}(?:-[A-Za-z]{2})?", normalized
        ):
            raise ValueError("language must be 'auto' or a short language code")
        return normalized

    @field_validator("allowed_domains", "blocked_domains")
    @classmethod
    def normalize_domains(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        normalized = list(dict.fromkeys(_normalize_domain(value) for value in values))
        return normalized or None

    @model_validator(mode="after")
    def validate_domain_filters(self) -> "WebSearchInput":
        if self.allowed_domains and self.blocked_domains:
            raise ValueError("allowed_domains and blocked_domains are mutually exclusive")
        return self


class WebSearchResult(ContractModel):
    """One normalized discovery result. Snippets are untrusted external data."""

    source_id: str = Field(pattern=r"^src_[0-9a-f]{16}$")
    title: str = Field(min_length=1, max_length=2_000)
    url: str = Field(min_length=1, max_length=8_000)
    domain: str = Field(min_length=1, max_length=253)
    snippet: str = Field(default="", max_length=8_000)
    engines: list[str] = Field(default_factory=list, max_length=32)
    published_at: datetime | None = None
    score: float | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _validate_http_url(value)

    @field_validator("domain")
    @classmethod
    def normalize_domain(cls, value: str) -> str:
        return _normalize_domain(value)

    @model_validator(mode="after")
    def validate_url_domain(self) -> "WebSearchResult":
        hostname = urlsplit(self.url).hostname
        if hostname is None or _normalize_domain(hostname) != self.domain:
            raise ValueError("domain must match the result URL hostname")
        return self


class WebSearchOutput(ContractModel):
    original_query: str = Field(min_length=1, max_length=500)
    results: list[WebSearchResult] = Field(default_factory=list, max_length=20)
    warnings: list[str] = Field(default_factory=list, max_length=20)


class WebFetchInput(ContractModel):
    """Input for opening one public HTTP(S) page discovered by search."""

    url: str = Field(min_length=1, max_length=8_000)
    max_characters: int = Field(default=12_000, ge=1_000, le=40_000)

    @field_validator("url")
    @classmethod
    def validate_public_url_shape(cls, value: str) -> str:
        return _validate_http_url(value)


class WebFetchOutput(ContractModel):
    source_id: str = Field(pattern=r"^src_[0-9a-f]{16}$")
    final_url: str = Field(min_length=1, max_length=8_000)
    title: str | None = Field(default=None, max_length=2_000)
    text: str = Field(min_length=1, max_length=40_000)
    content_type: str = Field(min_length=1, max_length=256)
    retrieved_at: datetime
    truncated: bool = False
    content_is_untrusted: Literal[True] = True

    @field_validator("final_url")
    @classmethod
    def validate_final_url(cls, value: str) -> str:
        return _validate_http_url(value)


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

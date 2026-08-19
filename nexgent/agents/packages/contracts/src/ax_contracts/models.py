"""Pydantic contracts crossing package, process, or persistence boundaries."""

import re
from datetime import UTC, date, datetime, time, timedelta
from ipaddress import ip_address
from math import isclose
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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


_DOCUMENT_MEDIA_TYPES = frozenset({"text/plain", "text/markdown", "text/csv"})
_IMAGE_MEDIA_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})


class ChatAttachmentRef(ContractModel):
    """Reference to one gateway-normalized, transient chat attachment."""

    attachment_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    filename: str = Field(min_length=1, max_length=255)
    kind: Literal["document", "image"]
    media_type: str = Field(min_length=1, max_length=128)
    uri: str = Field(min_length=1, max_length=4_096)
    byte_size: int = Field(ge=1, le=10 * 1024 * 1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("filename")
    @classmethod
    def validate_safe_filename(cls, value: str) -> str:
        if value in {".", ".."} or "/" in value or "\\" in value:
            raise ValueError("filename must be a basename")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("filename must not contain control characters")
        return value

    @field_validator("uri")
    @classmethod
    def validate_local_file_uri(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "file"
            or parsed.netloc not in {"", "localhost"}
            or not parsed.path.startswith("/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("uri must be an absolute local file URI")
        return value

    @model_validator(mode="after")
    def validate_media_type_for_kind(self) -> "ChatAttachmentRef":
        allowed = (
            _DOCUMENT_MEDIA_TYPES if self.kind == "document" else _IMAGE_MEDIA_TYPES
        )
        if self.media_type not in allowed:
            raise ValueError(f"media_type is not supported for {self.kind} attachments")
        return self


class ChatErrorPayload(ContractModel):
    """Safe error included in chat custom events and terminal graph state."""

    code: Literal[
        "attachment_invalid",
        "attachment_not_found",
        "attachment_too_large",
        "attachment_integrity_error",
        "attachment_unreadable",
        "vision_not_supported",
    ]
    message: str = Field(min_length=1, max_length=500)
    filename: str | None = Field(default=None, min_length=1, max_length=255)


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


class McpToolDefinition(ContractModel):
    """Normalized metadata for one tool discovered from an MCP server."""

    server_name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    name: str = Field(min_length=1, max_length=128)
    title: str | None = Field(default=None, max_length=512)
    description: str | None = Field(default=None, max_length=8_000)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    risk: Literal["read", "write", "destructive"] | None = None

    @field_validator("input_schema")
    @classmethod
    def validate_input_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        schema_type = value.get("type")
        if schema_type not in {None, "object"}:
            raise ValueError("MCP tool input schema must describe an object")
        return value


class McpToolCallResult(ContractModel):
    """Normalized, explicitly untrusted result returned by a remote MCP tool."""

    server_name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    tool_name: str = Field(min_length=1, max_length=128)
    content: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    structured_content: Any = None
    is_error: bool = False
    content_is_untrusted: Literal[True] = True


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
            raise ValueError(
                "allowed_domains and blocked_domains are mutually exclusive"
            )
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


class WeeklyReportRequest(ContractModel):
    """Boundary input for one manually triggered weekly-report batch."""

    week_start: date
    timezone: str = Field(default="Asia/Seoul", min_length=1, max_length=128)
    ward_ids: list[int] | None = Field(default=None, min_length=1, max_length=25)
    cursor: str | None = Field(default=None, min_length=1, max_length=2_000)
    limit: int = Field(default=25, ge=1, le=25)

    @field_validator("week_start")
    @classmethod
    def validate_monday(cls, value: date) -> date:
        if value.weekday() != 0:
            raise ValueError("week_start must be a Monday")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value

    @field_validator("ward_ids")
    @classmethod
    def validate_ward_ids(cls, values: list[int] | None) -> list[int] | None:
        if values is None:
            return None
        if any(value < 1 for value in values):
            raise ValueError("ward_ids must contain positive integers")
        if len(values) != len(set(values)):
            raise ValueError("ward_ids must be unique")
        return sorted(values)

    @model_validator(mode="after")
    def validate_selection(self) -> "WeeklyReportRequest":
        if self.ward_ids is not None and self.cursor is not None:
            raise ValueError("ward_ids and cursor are mutually exclusive")
        return self

    @property
    def week_end(self) -> date:
        """Exclusive end date for the requested reporting week."""

        return self.week_start + timedelta(days=7)


class WeeklyMetricSnapshot(ContractModel):
    """Deterministically calculated values for one seven-day period."""

    assigned_tasks: int = Field(ge=0)
    completed_tasks: int = Field(ge=0)
    completion_rate_percent: float = Field(ge=0, le=100)
    focus_minutes: int = Field(ge=0)
    active_days: int = Field(ge=0, le=7)
    blockers_opened: int = Field(ge=0)
    blockers_resolved: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_task_counts(self) -> "WeeklyMetricSnapshot":
        if self.completed_tasks > self.assigned_tasks:
            raise ValueError("completed_tasks must not exceed assigned_tasks")
        expected_rate = (
            round(self.completed_tasks / self.assigned_tasks * 100, 1)
            if self.assigned_tasks
            else 0.0
        )
        if self.completion_rate_percent != expected_rate:
            raise ValueError("completion_rate_percent must match the task counts")
        return self


class WeeklyMetricDelta(ContractModel):
    """Current week minus the immediately preceding week."""

    assigned_tasks: int
    completed_tasks: int
    completion_rate_percentage_points: float
    focus_minutes: int
    active_days: int
    blockers_opened: int
    blockers_resolved: int


class UserWeeklyMetrics(ContractModel):
    user_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=256)
    week_start: date
    week_end: date
    current: WeeklyMetricSnapshot
    previous: WeeklyMetricSnapshot
    delta: WeeklyMetricDelta

    @model_validator(mode="after")
    def validate_period(self) -> "UserWeeklyMetrics":
        if self.week_end != self.week_start + timedelta(days=7):
            raise ValueError("week_end must be seven days after week_start")
        return self


class UserWeeklyReport(ContractModel):
    user_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=256)
    metrics: UserWeeklyMetrics
    markdown: str = Field(min_length=1, max_length=40_000)
    generation_mode: Literal["llm", "template_fallback"]

    @model_validator(mode="after")
    def validate_identity(self) -> "UserWeeklyReport":
        if (
            self.user_id != self.metrics.user_id
            or self.display_name != self.metrics.display_name
        ):
            raise ValueError("report identity must match metrics identity")
        return self


class WeeklyReportBatchResult(ContractModel):
    status: Literal["completed"]
    week_start: date
    week_end: date
    timezone: str = Field(min_length=1, max_length=128)
    reports: list[UserWeeklyReport] = Field(min_length=1, max_length=100)
    warnings: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_batch(self) -> "WeeklyReportBatchResult":
        if self.week_end != self.week_start + timedelta(days=7):
            raise ValueError("week_end must be seven days after week_start")
        user_ids = [report.user_id for report in self.reports]
        if len(user_ids) != len(set(user_ids)):
            raise ValueError("reports must contain unique users")
        if user_ids != sorted(user_ids):
            raise ValueError("reports must be sorted by user_id")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return self


class WardWeeklyMetricSnapshot(ContractModel):
    """Deterministic metrics for one ward and one seven-day period."""

    covered_days: int = Field(default=0, ge=0, le=7)
    daily_summary_count: int = Field(default=0, ge=0)
    device_count: int = Field(default=0, ge=0)
    temperature_avg: float | None = None
    temperature_min: float | None = None
    temperature_max: float | None = None
    temperature_count: int = Field(default=0, ge=0)
    humidity_avg: float | None = None
    humidity_min: float | None = None
    humidity_max: float | None = None
    humidity_count: int = Field(default=0, ge=0)
    light_avg: float | None = None
    light_min: float | None = None
    light_max: float | None = None
    light_count: int = Field(default=0, ge=0)
    light_on_time_minutes_avg: float | None = None
    movement_count_avg: float | None = None
    remote_control_count_avg: float | None = None
    wake_up_time_avg: time | None = None
    sleep_time_avg: time | None = None
    night_awake_count_avg: float | None = None
    risk_detected_count: int = Field(default=0, ge=0)
    risk_resolved_count: int = Field(default=0, ge=0)
    risk_score_avg: float | None = None
    danger_days: int = Field(default=0, ge=0, le=7)
    dispatch_request_count: int = Field(default=0, ge=0)
    unresolved_dispatch_count: int = Field(default=0, ge=0)


class WardWeeklyMetricDelta(ContractModel):
    """Current week minus previous week for comparable metrics."""

    covered_days: int = Field(default=0, ge=-7, le=7)
    temperature_avg: float | None = None
    humidity_avg: float | None = None
    light_avg: float | None = None
    light_on_time_minutes_avg: float | None = None
    movement_count_avg: float | None = None
    remote_control_count_avg: float | None = None
    wake_up_time_minutes: float | None = None
    sleep_time_minutes: float | None = None
    night_awake_count_avg: float | None = None
    risk_detected_count: int = 0
    risk_resolved_count: int = 0
    risk_score_avg: float | None = None
    danger_days: int = Field(ge=-7, le=7)
    dispatch_request_count: int = 0
    unresolved_dispatch_count: int = 0


class WardWeeklyMetrics(ContractModel):
    """Grounded weekly danger-day comparison for one ward."""

    ward_id: int = Field(ge=1)
    display_name: str = Field(min_length=1, max_length=256)
    week_start: date
    week_end: date
    current: WardWeeklyMetricSnapshot
    previous: WardWeeklyMetricSnapshot
    delta: WardWeeklyMetricDelta

    @model_validator(mode="after")
    def validate_period_and_delta(self) -> "WardWeeklyMetrics":
        if self.week_end != self.week_start + timedelta(days=7):
            raise ValueError("week_end must be seven days after week_start")
        integer_fields = (
            "covered_days",
            "risk_detected_count",
            "risk_resolved_count",
            "danger_days",
            "dispatch_request_count",
            "unresolved_dispatch_count",
        )
        for field_name in integer_fields:
            expected = getattr(self.current, field_name) - getattr(
                self.previous, field_name
            )
            if getattr(self.delta, field_name) != expected:
                raise ValueError(f"{field_name} delta must match current minus previous")
        float_fields = (
            "temperature_avg",
            "humidity_avg",
            "light_avg",
            "light_on_time_minutes_avg",
            "movement_count_avg",
            "remote_control_count_avg",
            "night_awake_count_avg",
            "risk_score_avg",
        )
        for field_name in float_fields:
            _validate_optional_delta(
                field_name,
                getattr(self.current, field_name),
                getattr(self.previous, field_name),
                getattr(self.delta, field_name),
            )
        _validate_optional_delta(
            "wake_up_time_minutes",
            _clock_minutes(self.current.wake_up_time_avg),
            _clock_minutes(self.previous.wake_up_time_avg),
            self.delta.wake_up_time_minutes,
        )
        _validate_optional_delta(
            "sleep_time_minutes",
            _clock_minutes(self.current.sleep_time_avg),
            _clock_minutes(self.previous.sleep_time_avg),
            self.delta.sleep_time_minutes,
        )
        return self


def _clock_minutes(value: time | None) -> float | None:
    if value is None:
        return None
    return (value.hour * 3600 + value.minute * 60 + value.second) / 60


def _validate_optional_delta(
    field_name: str,
    current: float | None,
    previous: float | None,
    actual: float | None,
) -> None:
    if current is None or previous is None:
        if actual is not None:
            raise ValueError(f"{field_name} delta must be unavailable")
        return
    expected = current - previous
    if actual is None or not isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError(f"{field_name} delta must match current minus previous")


class WeeklyNarrative(ContractModel):
    """Validated human-facing Korean prose generated from allowlisted facts."""

    headline: str = Field(min_length=1, max_length=160)
    analysis_text: str = Field(min_length=80, max_length=500)
    observations: list[str] = Field(min_length=1, max_length=3)
    suggestions: list[str] = Field(default_factory=list, max_length=3)


class NarrativeGenerationMetadata(ContractModel):
    prompt_version: str = Field(min_length=1, max_length=64)
    model: str | None = Field(default=None, max_length=256)
    validation_status: Literal["passed", "fallback"]
    fallback_reason: str | None = Field(default=None, max_length=256)


class SkippedWard(ContractModel):
    ward_id: int = Field(ge=1)
    reason: Literal["not_found", "source_error"]


class WardWeeklyReport(ContractModel):
    ward_id: int = Field(ge=1)
    display_name: str = Field(min_length=1, max_length=256)
    metrics: WardWeeklyMetrics
    narrative: WeeklyNarrative
    markdown: str = Field(min_length=1, max_length=40_000)
    generation_mode: Literal["llm", "template_fallback"]
    generation: NarrativeGenerationMetadata

    @model_validator(mode="after")
    def validate_identity(self) -> "WardWeeklyReport":
        if (
            self.ward_id != self.metrics.ward_id
            or self.display_name != self.metrics.display_name
        ):
            raise ValueError("report identity must match ward metrics identity")
        return self


class WardWeeklyReportBatchResult(ContractModel):
    status: Literal["completed"]
    week_start: date
    week_end: date
    timezone: str = Field(min_length=1, max_length=128)
    reports: list[WardWeeklyReport] = Field(default_factory=list, max_length=25)
    skipped: list[SkippedWard] = Field(default_factory=list, max_length=25)
    next_cursor: str | None = Field(default=None, max_length=2_000)
    warnings: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_batch(self) -> "WardWeeklyReportBatchResult":
        if self.week_end != self.week_start + timedelta(days=7):
            raise ValueError("week_end must be seven days after week_start")
        ward_ids = [report.ward_id for report in self.reports]
        if len(ward_ids) != len(set(ward_ids)):
            raise ValueError("reports must contain unique wards")
        if ward_ids != sorted(ward_ids):
            raise ValueError("reports must be sorted by ward_id")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return self


class WeeklyReportSourceResponse(ContractModel):
    """Private FastAPI response consumed by the weekly-report workflow."""

    week_start: date
    week_end: date
    timezone: str = Field(min_length=1, max_length=128)
    items: list[WardWeeklyMetrics] = Field(default_factory=list, max_length=25)
    skipped: list[SkippedWard] = Field(default_factory=list, max_length=25)
    next_cursor: str | None = Field(default=None, max_length=2_000)
    warnings: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_period(self) -> "WeeklyReportSourceResponse":
        if self.week_end != self.week_start + timedelta(days=7):
            raise ValueError("week_end must be seven days after week_start")
        return self


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

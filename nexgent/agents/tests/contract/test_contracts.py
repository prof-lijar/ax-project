import pytest
from ax_contracts import (
    AgentInput,
    ChatAttachmentRef,
    RunContext,
    ToolRequest,
    WardWeeklyMetricDelta,
    WardWeeklyMetrics,
    WardWeeklyMetricSnapshot,
    WebFetchInput,
    WebSearchInput,
    WebSearchResult,
    WeeklyMetricSnapshot,
    WeeklyReportRequest,
)
from pydantic import ValidationError


def test_contracts_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        AgentInput(message="hello", secret="must-not-cross-boundary")  # type: ignore[call-arg]


def test_context_has_thread_and_correlation_identity() -> None:
    context = RunContext(tenant_id="tenant-a")
    assert context.correlation_id
    assert context.tenant_id == "tenant-a"


def test_tool_request_requires_idempotency_key() -> None:
    with pytest.raises(ValidationError):
        ToolRequest(tool_name="lookup", arguments={})  # type: ignore[call-arg]


def test_chat_attachment_reference_is_strict_and_kind_safe() -> None:
    reference = ChatAttachmentRef(
        attachment_id="upload_123",
        filename="notes.txt",
        kind="document",
        media_type="text/plain",
        uri="file:///var/lib/ax-chat/upload_123/normalized.txt",
        byte_size=12,
        sha256="a" * 64,
    )
    assert reference.filename == "notes.txt"

    with pytest.raises(ValidationError, match="basename"):
        ChatAttachmentRef(
            **(reference.model_dump(exclude={"filename"}) | {"filename": "../notes.txt"})
        )
    with pytest.raises(ValidationError, match="not supported"):
        ChatAttachmentRef(
            **(
                reference.model_dump(exclude={"media_type"})
                | {"media_type": "image/png"}
            )
        )
    with pytest.raises(ValidationError, match="local file URI"):
        ChatAttachmentRef(
            **(reference.model_dump(exclude={"uri"}) | {"uri": "https://example.com/a"})
        )
    with pytest.raises(ValidationError):
        ChatAttachmentRef(**(reference.model_dump() | {"unexpected": True}))


def test_web_search_contract_normalizes_domains_and_rejects_conflicting_filters() -> (
    None
):
    input = WebSearchInput(
        query="current LangGraph release", allowed_domains=["Docs.LangChain.com."]
    )
    assert input.allowed_domains == ["docs.langchain.com"]

    with pytest.raises(ValidationError, match="mutually exclusive"):
        WebSearchInput(
            query="current LangGraph release",
            allowed_domains=["langchain.com"],
            blocked_domains=["example.com"],
        )


def test_web_contracts_reject_unknown_fields_and_credential_urls() -> None:
    with pytest.raises(ValidationError):
        WebSearchInput(query="hello", unrestricted=True)  # type: ignore[call-arg]

    with pytest.raises(ValidationError, match="credentials"):
        WebFetchInput(url="https://user:secret@example.com/private")

    with pytest.raises(ValidationError, match="domain must match"):
        WebSearchResult(
            source_id="src_0123456789abcdef",
            title="mismatched source",
            url="https://example.com/page",
            domain="attacker.example",
        )


def test_weekly_report_request_validates_period_and_timezone() -> None:
    request = WeeklyReportRequest(week_start="2026-08-03")
    assert request.week_end.isoformat() == "2026-08-10"
    assert request.timezone == "Asia/Seoul"
    assert WeeklyReportRequest(week_start="2026-08-03", limit=100).limit == 100

    with pytest.raises(ValidationError, match="Monday"):
        WeeklyReportRequest(week_start="2026-08-04")
    with pytest.raises(ValidationError, match="IANA"):
        WeeklyReportRequest(week_start="2026-08-03", timezone="Mars/Olympus")
    with pytest.raises(ValidationError):
        WeeklyReportRequest(week_start="2026-08-03", unknown=True)  # type: ignore[call-arg]
    with pytest.raises(ValidationError, match="mutually exclusive"):
        WeeklyReportRequest(week_start="2026-08-03", ward_ids=[1], cursor="opaque")
    with pytest.raises(ValidationError, match="unique"):
        WeeklyReportRequest(week_start="2026-08-03", ward_ids=[1, 1])
    with pytest.raises(ValidationError):
        WeeklyReportRequest(week_start="2026-08-03", limit=101)


def test_weekly_metric_snapshot_rejects_inconsistent_calculations() -> None:
    with pytest.raises(ValidationError, match="must match"):
        WeeklyMetricSnapshot(
            assigned_tasks=10,
            completed_tasks=8,
            completion_rate_percent=75,
            focus_minutes=300,
            active_days=4,
            blockers_opened=1,
            blockers_resolved=1,
        )

    with pytest.raises(ValidationError, match="must not exceed"):
        WeeklyMetricSnapshot(
            assigned_tasks=1,
            completed_tasks=2,
            completion_rate_percent=100,
            focus_minutes=0,
            active_days=1,
            blockers_opened=0,
            blockers_resolved=0,
        )


def test_ward_weekly_metrics_reject_inconsistent_delta() -> None:
    with pytest.raises(ValidationError, match="delta must match"):
        WardWeeklyMetrics(
            ward_id=101,
            display_name="관리 대상 101",
            week_start="2026-08-03",
            week_end="2026-08-10",
            current=WardWeeklyMetricSnapshot(danger_days=2),
            previous=WardWeeklyMetricSnapshot(danger_days=1),
            delta=WardWeeklyMetricDelta(danger_days=0),
        )

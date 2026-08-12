import pytest
from ax_contracts import (
    AgentInput,
    RunContext,
    ToolRequest,
    WebFetchInput,
    WebSearchInput,
    WebSearchResult,
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


def test_web_search_contract_normalizes_domains_and_rejects_conflicting_filters() -> None:
    input = WebSearchInput(query="current LangGraph release", allowed_domains=["Docs.LangChain.com."])
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

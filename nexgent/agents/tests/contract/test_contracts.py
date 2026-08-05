import pytest
from ax_contracts import AgentInput, RunContext, ToolRequest
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

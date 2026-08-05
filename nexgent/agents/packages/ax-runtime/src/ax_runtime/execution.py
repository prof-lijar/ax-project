from dataclasses import dataclass
from typing import Any

from ax_contracts import RunContext


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    """Boundaries enforced by callers and tool adapters."""

    timeout_seconds: float = 120.0
    max_attempts: int = 3
    max_tool_calls: int = 32


def build_config(context: RunContext) -> dict[str, Any]:
    """Build the LangGraph configurable context without leaking secrets."""

    return {
        "configurable": {
            "thread_id": context.thread_id or str(context.correlation_id),
            "tenant_id": context.tenant_id,
            "correlation_id": str(context.correlation_id),
        },
        "tags": ["ax-agent", f"tenant:{context.tenant_id}"],
        "metadata": {"correlation_id": str(context.correlation_id)},
    }

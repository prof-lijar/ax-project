from dataclasses import dataclass

from ax_contracts import ToolRequest


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    """Allowlist and risk policy evaluated before every tool call."""

    allowed_tools: frozenset[str] = frozenset()
    allow_writes: bool = False
    allow_destructive: bool = False


def authorize(request: ToolRequest, policy: ToolPolicy) -> None:
    if request.tool_name not in policy.allowed_tools:
        raise PermissionError(f"tool is not allowlisted: {request.tool_name}")
    if request.risk == "write" and not policy.allow_writes:
        raise PermissionError("write tools are disabled by policy")
    if request.risk == "destructive" and not policy.allow_destructive:
        raise PermissionError("destructive tools are disabled by policy")

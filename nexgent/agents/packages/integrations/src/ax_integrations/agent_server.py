from collections.abc import AsyncIterator
from typing import Any, Protocol

from ax_contracts import AgentInput


class AgentServerClient(Protocol):
    async def submit(self, assistant_id: str, input: AgentInput) -> dict[str, Any]: ...

    async def get(self, run_id: str) -> dict[str, Any]: ...

    async def stream(self, run_id: str) -> AsyncIterator[dict[str, Any]]: ...

    async def resume(self, thread_id: str, command: dict[str, Any]) -> dict[str, Any]: ...


class AgentServerUnavailable(RuntimeError):
    """Raised when the gateway has no configured Agent Server adapter."""

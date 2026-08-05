from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    TOOL_DENIED = "tool_denied"
    TOOL_TIMEOUT = "tool_timeout"
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    INTERRUPTED = "interrupted"


class AgentRuntimeError(Exception):
    """Normalized runtime error with an explicit retry decision."""

    def __init__(self, code: ErrorCode, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable

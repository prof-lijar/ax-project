"""Pure nodes owned by the deterministic smoke workflow."""

from .state import SmokeState


def acknowledge(state: SmokeState) -> SmokeState:
    message = state.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message must be a non-empty string")
    return {"response": f"ack: {message.strip()}"}

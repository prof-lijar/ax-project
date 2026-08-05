"""State local to the deterministic smoke workflow."""

from typing import TypedDict


class SmokeState(TypedDict, total=False):
    message: str
    response: str

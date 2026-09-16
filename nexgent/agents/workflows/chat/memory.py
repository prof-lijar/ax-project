"""Retain recent complete text turns without growing model context indefinitely."""

from .state import ChatTurn

MAX_HISTORY_TURNS = 20
MAX_HISTORY_CHARACTERS = 32_000


def bounded_history(turns: list[ChatTurn]) -> list[ChatTurn]:
    """Keep a contiguous suffix of whole turns within both limits."""
    retained: list[ChatTurn] = []
    size = 0
    for turn in reversed(turns[-MAX_HISTORY_TURNS:]):
        turn_size = len(turn["user"]) + len(turn["assistant"])
        if size + turn_size > MAX_HISTORY_CHARACTERS:
            break
        retained.append(turn)
        size += turn_size
    return list(reversed(retained))

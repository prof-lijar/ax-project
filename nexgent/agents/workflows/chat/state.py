"""Minimal state for one chat-completion turn."""

from typing import TypedDict


class ChatState(TypedDict, total=False):
    message: str
    response: str

"""Minimal state for one grounded RAG chat turn."""

from typing import NotRequired, TypedDict


class RagChatErrorState(TypedDict):
    schema_version: str
    code: str
    message: str


class RagChatState(TypedDict, total=False):
    message: str
    response: str
    error: NotRequired[RagChatErrorState]

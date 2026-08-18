"""Minimal state for one chat-completion turn."""

from typing import NotRequired, TypedDict

from ax_contracts import ChatAttachmentRef


class ChatErrorState(TypedDict):
    schema_version: str
    code: str
    message: str
    filename: NotRequired[str | None]


class ChatState(TypedDict, total=False):
    message: str
    attachments: list[ChatAttachmentRef]
    response: str
    error: ChatErrorState

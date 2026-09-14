"""Current turn and bounded conversation history, checkpointed per thread."""

from typing import NotRequired, TypedDict

from ax_contracts import ChatAttachmentRef


class ChatErrorState(TypedDict):
    schema_version: str
    code: str
    message: str
    filename: NotRequired[str | None]


class ChatTurn(TypedDict):
    user: str
    assistant: str


class ChatState(TypedDict, total=False):
    message: str
    attachments: list[ChatAttachmentRef]
    response: str
    error: ChatErrorState | None
    history: list[ChatTurn]

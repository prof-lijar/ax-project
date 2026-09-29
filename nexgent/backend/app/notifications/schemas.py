from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, field_validator, model_validator

Destination = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
RequestKey = Annotated[str, StringConstraints(pattern=r"^[\x21-\x7e]{1,128}$")]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NotificationField(Input):
    name: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=1000)


TableCell = Annotated[str, StringConstraints(min_length=1, max_length=1000)]


class NotificationTable(Input):
    columns: list[TableCell] = Field(min_length=1, max_length=20)
    rows: list[list[TableCell]] = Field(min_length=1, max_length=99)
    align: list[Literal["left", "center", "right"]] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def valid_table(self):
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("Table rows must match the column count")
        if self.align and len(self.align) != len(self.columns):
            raise ValueError("Table alignment must match the column count")
        if sum(len(cell) for row in [self.columns, *self.rows] for cell in row) > 10000:
            raise ValueError("Slack table cells must total at most 10000 characters")
        return self


class BlockText(Input):
    type: Literal["plain_text", "mrkdwn"]
    text: str = Field(min_length=1, max_length=3000)
    emoji: bool | None = None
    verbatim: bool | None = None

    @model_validator(mode="after")
    def valid_text(self):
        if self.type == "plain_text" and self.verbatim is not None:
            raise ValueError("verbatim applies only to mrkdwn")
        if self.type == "mrkdwn" and self.emoji is not None:
            raise ValueError("emoji applies only to plain_text")
        if self.type == "mrkdwn" and len(escaped_text(self.text)) > 3000:
            raise ValueError("Escaped mrkdwn text exceeds 3000 characters")
        return self


def escaped_text(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class NativeBlockInput(Input):
    block_id: str | None = Field(default=None, min_length=1, max_length=255)


class HeaderBlock(NativeBlockInput):
    type: Literal["header"]
    text: BlockText

    @model_validator(mode="after")
    def valid_header(self):
        if self.text.type != "plain_text" or len(self.text.text) > 150:
            raise ValueError("Header requires plain text of at most 150 characters")
        return self


class SectionBlock(NativeBlockInput):
    type: Literal["section"]
    text: BlockText | None = None
    fields: list[BlockText] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def valid_section(self):
        if self.text is None and not self.fields:
            raise ValueError("Section requires text or fields")
        if any(len(escaped_text(field.text) if field.type == "mrkdwn" else field.text) > 2000 for field in self.fields):
            raise ValueError("Section fields must be at most 2000 characters")
        return self


class ContextBlock(NativeBlockInput):
    type: Literal["context"]
    elements: list[BlockText] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def valid_context(self):
        if any(len(escaped_text(element.text) if element.type == "mrkdwn" else element.text) > 2000 for element in self.elements):
            raise ValueError("Context text must be at most 2000 characters")
        return self


class DividerBlock(NativeBlockInput):
    type: Literal["divider"]


class TableTextCell(Input):
    type: Literal["raw_text"]
    text: TableCell


class TableColumn(Input):
    align: Literal["left", "center", "right"] = "left"
    is_wrapped: bool = False


class TableBlock(NativeBlockInput):
    type: Literal["table"]
    rows: list[list[TableTextCell]] = Field(min_length=1, max_length=100)
    column_settings: list[TableColumn] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def valid_rows(self):
        width = len(self.rows[0])
        if not 1 <= width <= 20 or any(len(row) != width for row in self.rows):
            raise ValueError("Table must be rectangular with 1 to 20 columns")
        if len(self.column_settings) > width:
            raise ValueError("Too many column settings")
        return self


NativeBlock = Annotated[
    HeaderBlock | SectionBlock | ContextBlock | DividerBlock | TableBlock,
    Field(discriminator="type"),
]


class SlackNotification(Input):
    destination: Destination = "default"
    text: str = Field(min_length=1, max_length=4000)
    title: str | None = Field(default=None, min_length=1, max_length=150)
    severity: Literal["info", "success", "warning", "error"] = "info"
    fields: list[NotificationField] = Field(default_factory=list, max_length=10)
    table: NotificationTable | None = None
    footer: str | None = Field(default=None, min_length=1, max_length=3000)
    locale: Literal["en", "ko"] | None = None
    blocks: list[NativeBlock] = Field(default_factory=list, max_length=50)
    url: HttpUrl | None = None
    thread_ts: str | None = Field(default=None, pattern=r"^\d{10,}\.[0-9]{6}$", max_length=32)

    @model_validator(mode="after")
    def valid_native_layout(self):
        if not self.blocks:
            return self
        if self.table or self.fields or self.title or self.footer or self.url:
            raise ValueError("Native blocks cannot be combined with generated layout fields")
        characters = sum(
            len(cell.text) for block in self.blocks if isinstance(block, TableBlock)
            for row in block.rows for cell in row
        )
        if characters > 10000:
            raise ValueError("All table cells together must total at most 10000 characters")
        if sum(isinstance(block, TableBlock) for block in self.blocks) > 1:
            raise ValueError("At most one table block is supported per notification")
        def text_size(value):
            if isinstance(value, dict):
                return sum(len(escaped_text(item)) if key == "text" and isinstance(item, str)
                           else text_size(item) for key, item in value.items())
            if isinstance(value, list):
                return sum(text_size(item) for item in value)
            return 0
        if len(escaped_text(self.text)) + sum(text_size(block.model_dump()) for block in self.blocks) > 30000:
            raise ValueError("Native notification text exceeds the accessible fallback budget")
        block_ids = [block.block_id for block in self.blocks if block.block_id]
        if len(set(block_ids)) != len(block_ids):
            raise ValueError("Block IDs must be unique")
        return self

    @field_validator("url")
    @classmethod
    def safe_link(cls, value):
        if value and (value.username or value.password or len(str(value)) > 2000):
            raise ValueError("Notification links must not contain credentials and must be at most 2000 characters")
        return value


class NotificationStatus(BaseModel):
    id: UUID
    provider: Literal["slack"] = "slack"
    destination: str
    status: Literal["queued", "sending", "sent", "failed"]
    attempts: int
    created_at: datetime
    updated_at: datetime
    sent_at: datetime | None
    error_code: str | None
    slack_ts: str | None


class NotificationCapabilities(BaseModel):
    enabled: bool
    destinations: list[str]

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, field_validator

Destination = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
RequestKey = Annotated[str, StringConstraints(pattern=r"^[\x21-\x7e]{1,128}$")]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NotificationField(Input):
    name: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=1000)


class SlackNotification(Input):
    destination: Destination = "default"
    text: str = Field(min_length=1, max_length=4000)
    title: str | None = Field(default=None, min_length=1, max_length=150)
    severity: Literal["info", "success", "warning", "error"] = "info"
    fields: list[NotificationField] = Field(default_factory=list, max_length=10)
    url: HttpUrl | None = None
    thread_ts: str | None = Field(default=None, pattern=r"^\d{10,}\.[0-9]{6}$", max_length=32)

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

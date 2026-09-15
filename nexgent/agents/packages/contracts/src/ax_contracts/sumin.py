"""Normalized, replayable Sumin work; raw Slack envelopes never enter the graph."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SuminTask(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["sumin-v1"] = "sumin-v1"
    event_id: str = Field(pattern=r"^Ev[A-Za-z0-9]+$", max_length=80)
    team_id: str = Field(pattern=r"^T[A-Z0-9]+$", max_length=40)
    channel_id: str = Field(pattern=r"^[CG][A-Z0-9]+$", max_length=40)
    kind: Literal["archive", "search"]
    file_id: str | None = Field(default=None, pattern=r"^F[A-Z0-9]+$", max_length=40)
    user_id: str = Field(default="", max_length=40)
    text: str = Field(default="", max_length=40000)
    message_ts: str | None = Field(default=None, pattern=r"^\d{1,16}\.\d{1,16}$")
    thread_ts: str | None = Field(default=None, pattern=r"^\d{1,16}\.\d{1,16}$")

    @model_validator(mode="after")
    def validate_kind(self):
        if self.kind == "archive" and self.file_id is None:
            raise ValueError("archive requires file_id")
        if self.kind == "search" and (
            self.file_id is not None or self.message_ts is None
        ):
            raise ValueError("search requires message_ts and no file_id")
        return self

    @property
    def key(self) -> str:
        return f"{self.team_id}:{self.event_id}:{self.file_id or 'search'}"

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatAttachmentRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"] = "1"
    attachment_id: str = Field(min_length=36, max_length=36)
    filename: str = Field(min_length=1, max_length=255)
    kind: Literal["document", "image"]
    media_type: str = Field(min_length=1, max_length=100)
    uri: str = Field(pattern=r"^file:///")
    byte_size: int = Field(gt=0, le=50 * 1024 * 1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ChatErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    code: str
    message: str
    filename: str | None = None


class ChatErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ChatErrorDetail

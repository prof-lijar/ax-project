import unicodedata
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict


def validate_name(value: str) -> str:
    value = unicodedata.normalize("NFC", value).strip()
    if (not value or value in {".", ".."} or len(value.encode("utf-8")) > 255
            or any(c in "/\\" or unicodedata.category(c).startswith("C") for c in value)):
        raise ValueError("Use a name of 1–255 UTF-8 bytes without separators or control characters")
    return value


Name = Annotated[str, AfterValidator(validate_name)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FolderInput(Input):
    name: Name
    parent_id: UUID | None = None


class RenameInput(Input):
    name: Name


class DestinationInput(Input):
    parent_id: UUID | None = None
    name: Name | None = None


class RestoreInput(Input):
    # Omitted preserves the original parent; explicit null restores to root.
    parent_id: UUID | None = None
    name: Name | None = None

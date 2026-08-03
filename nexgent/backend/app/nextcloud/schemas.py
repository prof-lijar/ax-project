from pydantic import BaseModel, Field


class FileItem(BaseModel):
    path: str
    name: str
    is_directory: bool
    content_type: str | None = None
    size: int | None = None
    etag: str | None = None
    last_modified: str | None = None


class ListFilesResponse(BaseModel):
    path: str
    depth: int
    items: list[FileItem]


class TextFileResponse(BaseModel):
    path: str
    content: str
    content_type: str | None = None


class WriteTextRequest(BaseModel):
    content: str
    content_type: str = "text/plain; charset=utf-8"


class CreateFolderRequest(BaseModel):
    path: str = Field(..., min_length=1)


class CopyMoveRequest(BaseModel):
    source_path: str = Field(..., min_length=1)
    destination_path: str = Field(..., min_length=1)
    overwrite: bool = False


class OperationResponse(BaseModel):
    ok: bool
    path: str | None = None
    destination_path: str | None = None
    status_code: int | None = None
    detail: str | None = None


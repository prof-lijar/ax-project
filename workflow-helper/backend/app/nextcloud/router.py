from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.settings import SettingsError
from app.nextcloud.client import NextcloudClient, NextcloudError
from app.nextcloud.dependencies import get_nextcloud_client
from app.nextcloud.schemas import (
    CopyMoveRequest,
    CreateFolderRequest,
    ListFilesResponse,
    OperationResponse,
    TextFileResponse,
    WriteTextRequest,
)


router = APIRouter()


@router.get("/files", response_model=ListFilesResponse)
async def list_files(
    path: str = Query(default=""),
    depth: int = Query(default=1, ge=0, le=1),
    client: NextcloudClient = Depends(get_nextcloud_client),
) -> ListFilesResponse:
    try:
        items = await client.list_files(path=path, depth=depth)
        return ListFilesResponse(path=path, depth=depth, items=items)
    except (NextcloudError, SettingsError) as exc:
        raise _to_http_exception(exc) from exc


@router.get("/files/content", response_model=TextFileResponse)
async def read_text_file(
    path: str = Query(..., min_length=1),
    client: NextcloudClient = Depends(get_nextcloud_client),
) -> TextFileResponse:
    try:
        content, content_type = await client.read_text_file(path)
        return TextFileResponse(path=path, content=content, content_type=content_type)
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=415, detail="File is not decodable as text.") from exc
    except (NextcloudError, SettingsError) as exc:
        raise _to_http_exception(exc) from exc


@router.get("/files/download")
async def download_file(
    path: str = Query(..., min_length=1),
    client: NextcloudClient = Depends(get_nextcloud_client),
) -> StreamingResponse:
    try:
        downloaded = await client.download_file(path)
        headers = {"Content-Disposition": f'attachment; filename="{downloaded.filename}"'}
        return StreamingResponse(
            iter([downloaded.content]),
            media_type=downloaded.content_type or "application/octet-stream",
            headers=headers,
        )
    except (NextcloudError, SettingsError) as exc:
        raise _to_http_exception(exc) from exc


@router.put("/files/content", response_model=OperationResponse)
async def write_text_file(
    payload: WriteTextRequest,
    path: str = Query(..., min_length=1),
    client: NextcloudClient = Depends(get_nextcloud_client),
) -> OperationResponse:
    try:
        status_code = await client.write_text_file(path, payload.content, payload.content_type)
        return OperationResponse(ok=True, path=path, status_code=status_code)
    except (NextcloudError, SettingsError) as exc:
        raise _to_http_exception(exc) from exc


@router.put("/files/upload", response_model=OperationResponse)
async def upload_file(
    path: str = Query(..., min_length=1),
    file: UploadFile = File(...),
    client: NextcloudClient = Depends(get_nextcloud_client),
) -> OperationResponse:
    try:
        status_code = await client.upload_file(
            path=path,
            content=await file.read(),
            content_type=file.content_type,
        )
        return OperationResponse(ok=True, path=path, status_code=status_code)
    except (NextcloudError, SettingsError) as exc:
        raise _to_http_exception(exc) from exc


@router.post("/folders", response_model=OperationResponse)
async def create_folder(
    payload: CreateFolderRequest,
    client: NextcloudClient = Depends(get_nextcloud_client),
) -> OperationResponse:
    try:
        status_code = await client.create_folder(payload.path)
        detail = "Folder already exists." if status_code == 405 else None
        return OperationResponse(ok=True, path=payload.path, status_code=status_code, detail=detail)
    except (NextcloudError, SettingsError) as exc:
        raise _to_http_exception(exc) from exc


@router.delete("/files", response_model=OperationResponse)
async def delete_file_or_folder(
    path: str = Query(..., min_length=1),
    client: NextcloudClient = Depends(get_nextcloud_client),
) -> OperationResponse:
    try:
        status_code = await client.delete(path)
        return OperationResponse(ok=True, path=path, status_code=status_code)
    except (NextcloudError, SettingsError) as exc:
        raise _to_http_exception(exc) from exc


@router.post("/files/copy", response_model=OperationResponse)
async def copy_file_or_folder(
    payload: CopyMoveRequest,
    client: NextcloudClient = Depends(get_nextcloud_client),
) -> OperationResponse:
    try:
        status_code = await client.copy(
            payload.source_path,
            payload.destination_path,
            payload.overwrite,
        )
        return OperationResponse(
            ok=True,
            path=payload.source_path,
            destination_path=payload.destination_path,
            status_code=status_code,
        )
    except (NextcloudError, SettingsError) as exc:
        raise _to_http_exception(exc) from exc


@router.post("/files/move", response_model=OperationResponse)
async def move_file_or_folder(
    payload: CopyMoveRequest,
    client: NextcloudClient = Depends(get_nextcloud_client),
) -> OperationResponse:
    try:
        status_code = await client.move(
            payload.source_path,
            payload.destination_path,
            payload.overwrite,
        )
        return OperationResponse(
            ok=True,
            path=payload.source_path,
            destination_path=payload.destination_path,
            status_code=status_code,
        )
    except (NextcloudError, SettingsError) as exc:
        raise _to_http_exception(exc) from exc


@router.get("/capabilities")
async def get_capabilities(
    client: NextcloudClient = Depends(get_nextcloud_client),
) -> JSONResponse:
    try:
        return JSONResponse(content=await client.capabilities())
    except (NextcloudError, SettingsError) as exc:
        raise _to_http_exception(exc) from exc


def _to_http_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, NextcloudError):
        return HTTPException(status_code=exc.status_code or 502, detail=exc.message)
    if isinstance(exc, SettingsError):
        return HTTPException(status_code=500, detail=str(exc))
    return HTTPException(status_code=500, detail="Unexpected Nextcloud integration error.")

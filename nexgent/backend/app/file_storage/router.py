from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from app.file_storage.config import load_storage_settings
from app.file_storage.schemas import DestinationInput, FolderInput, RenameInput, RestoreInput
from app.file_storage.service import get_storage_client, upload
from app.file_storage.store import StorageStore
from app.file_storage.upload_tree import MAX_UPLOAD_FOLDERS, MAX_UPLOAD_DEPTH
from app.identity.store import AccessError
from app.nextcloud.client import DownloadedFile, NextcloudClient, NextcloudError


router = APIRouter(prefix="/api/file-storage", tags=["file-storage"])


def store_for(request: Request):
    if not hasattr(request.app.state, "file_storage_store"):
        settings = load_storage_settings()
        request.app.state.file_storage_store = StorageStore(request.app.state.identity_store.engine, settings.deployment)
    return request.app.state.file_storage_store


def owner(request):
    return request.state.account.user_id


def ident(value):
    return str(value) if value is not None else None


@router.get("/capabilities")
def capabilities():
    settings = load_storage_settings()
    return {"max_file_bytes": settings.max_file_bytes, "max_batch_bytes": settings.max_batch_bytes,
            "max_files": settings.max_files, "name_conflict_policy": "auto_rename",
            "case_sensitive_names": True, "trash": True, "folder_upload": True,
            "max_upload_folders": MAX_UPLOAD_FOLDERS, "max_upload_depth": MAX_UPLOAD_DEPTH}


@router.get("/entries")
def list_entries(request: Request, parent_id: UUID | None = None,
                 q: Annotated[str | None, Query(min_length=1, max_length=255)] = None,
                 limit: Annotated[int, Query(ge=1, le=200)] = 100,
                 offset: Annotated[int, Query(ge=0)] = 0):
    return store_for(request).list(owner(request), ident(parent_id), query=q, limit=limit, offset=offset)


@router.get("/trash")
def list_trash(request: Request, limit: Annotated[int, Query(ge=1, le=200)] = 100,
               offset: Annotated[int, Query(ge=0)] = 0):
    return store_for(request).list(owner(request), trash=True, limit=limit, offset=offset)


@router.post("/folders", status_code=201)
def create_folder(request: Request, body: FolderInput):
    return store_for(request).folder(owner(request), body.name, ident(body.parent_id))


@router.post("/files", status_code=201)
async def upload_files(request: Request, files: Annotated[list[UploadFile], File()] = [],
                       parent_id: Annotated[UUID | None, Form()] = None,
                       tree: Annotated[str | None, Form()] = None,
                       client=Depends(get_storage_client)):
    items = await upload(store_for(request), client, load_storage_settings(), owner(request), ident(parent_id), files, tree)
    return {"items": items}


@router.get("/entries/{entry_id}")
def get_entry(request: Request, entry_id: UUID):
    return store_for(request).detail(owner(request), str(entry_id))


@router.get("/entries/{entry_id}/download")
async def download(request: Request, entry_id: UUID, client=Depends(get_storage_client)):
    entry, path = await run_in_threadpool(store_for(request).download, owner(request), str(entry_id))
    try:
        downloaded = await client.download_file(path)
    except NextcloudError as exc:
        raise AccessError(502, "file_storage_upstream_error") from exc
    return Response(downloaded.content, media_type="application/octet-stream", headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(entry['name'], safe='')}",
        "X-Content-Type-Options": "nosniff",
    })


@router.get("/entries/{entry_id}/preview")
async def preview(request: Request, entry_id: UUID, client=Depends(get_storage_client)):
    # Resolve through the owner-scoped tree before accessing Nextcloud. Blob names
    # have no extension, so preview selection must use the current logical name.
    entry, path = await run_in_threadpool(store_for(request).download, owner(request), str(entry_id))
    try:
        downloaded = await client.download_file(path)
        rendered = await run_in_threadpool(NextcloudClient.render_preview, DownloadedFile(
            path=path, content=downloaded.content, content_type=entry["content_type"], filename=entry["name"],
        ))
    except NextcloudError as exc:
        codes = {415: "preview_unsupported", 501: "preview_converter_unavailable", 504: "preview_timeout"}
        raise AccessError(exc.status_code if exc.status_code in codes else 502,
                          codes.get(exc.status_code, "preview_failed")) from exc
    return Response(rendered.content, media_type=rendered.content_type, headers={
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(rendered.filename, safe='')}",
        "X-Preview-Kind": rendered.viewer_kind,
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox; default-src 'none'",
    })


@router.patch("/entries/{entry_id}")
def rename(request: Request, entry_id: UUID, body: RenameInput):
    return store_for(request).relocate(owner(request), str(entry_id), name=body.name)


@router.post("/entries/{entry_id}/move")
def move(request: Request, entry_id: UUID, body: DestinationInput):
    return store_for(request).relocate(owner(request), str(entry_id), name=body.name,
                                       parent=ident(body.parent_id), move=True)


@router.post("/entries/{entry_id}/copy", status_code=201)
def copy(request: Request, entry_id: UUID, body: DestinationInput):
    return store_for(request).copy(owner(request), str(entry_id), ident(body.parent_id), body.name)


@router.delete("/entries/{entry_id}", status_code=204)
def trash(request: Request, entry_id: UUID):
    store_for(request).trash(owner(request), str(entry_id))
    return Response(status_code=204)


@router.post("/trash/{entry_id}/restore")
def restore(request: Request, entry_id: UUID, body: RestoreInput):
    return store_for(request).restore(owner(request), str(entry_id), body.model_dump(mode="json", exclude_unset=True))


@router.delete("/trash/{entry_id}", status_code=204)
def purge(request: Request, entry_id: UUID):
    store_for(request).purge(owner(request), str(entry_id))
    return Response(status_code=204)

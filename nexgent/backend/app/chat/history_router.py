import asyncio
import json
import logging
import time
from typing import Annotated
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, Header, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.chat.config import get_chat_settings
from app.chat.errors import ChatRequestError
from app.chat.store import TERMINAL, ChatStore
from app.chat.vault import FileVault
from app.identity.store import AccessError

router = APIRouter()


def store_for(request):
    if not hasattr(request.app.state, "chat_store"):
        request.app.state.chat_store = ChatStore(
            request.app.state.identity_store.engine
        )
    return request.app.state.chat_store


def owner(request):
    return request.state.account.user_id


class Rename(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=120)


@router.get("/conversations")
def conversations(
    request: Request, cursor: str | None = None, limit: int = Query(30, ge=1, le=100)
):
    return store_for(request).conversations(owner(request), cursor, limit)


@router.get("/conversations/{ident}")
def conversation(request: Request, ident: UUID):
    return store_for(request).conversation(owner(request), str(ident))


@router.patch("/conversations/{ident}")
def rename(request: Request, ident: UUID, body: Rename):
    return store_for(request).rename(owner(request), str(ident), body.title)


@router.delete("/conversations/{ident}", status_code=204)
def remove(request: Request, ident: UUID):
    store_for(request).remove(owner(request), str(ident))


@router.get("/conversations/{ident}/messages")
def messages(
    request: Request,
    ident: UUID,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=100),
):
    return store_for(request).messages(owner(request), str(ident), cursor, limit)


@router.get("/conversations/{ident}/attachments")
def attachments(
    request: Request,
    ident: UUID,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=100),
):
    return store_for(request).attachments(owner(request), str(ident), cursor, limit)


async def submit(request, ident, prompt, files, attachment_ids, key):
    prompt = (prompt or "").strip()
    if not prompt:
        raise ChatRequestError("prompt_required", "A non-empty prompt is required.")
    if len(prompt) > 100_000:
        raise ChatRequestError(
            "invalid_prompt", "Enter a message of at most 100,000 characters."
        )
    if not key or len(key) > 128:
        raise ChatRequestError(
            "idempotency_key_required", "A submission key is required."
        )
    ids = list(dict.fromkeys(str(i) for i in attachment_ids or []))
    if len(ids) + len(files or []) > 5:
        raise ChatRequestError(
            "too_many_files", "Select at most five files.", status_code=413
        )
    if ids and not ident:
        raise AccessError(404, "not_found")
    store = store_for(request)
    if ident:
        await run_in_threadpool(store.conversation, owner(request), ident)
    selected = (
        await run_in_threadpool(store.selected_files, owner(request), ident, ids)
        if ids
        else []
    )
    vault = FileVault(get_chat_settings())
    prepared = await vault.prepare(files or [])
    try:
        await run_in_threadpool(vault.validate, [*prepared, *selected])
        result, _ = await run_in_threadpool(
            store.submit, owner(request), ident, prompt, key, prepared, selected
        )
        return result
    finally:
        for file in prepared:
            # A commit can have succeeded even if its response was lost.
            try:
                if not await run_in_threadpool(store.file_exists, file["id"]):
                    await run_in_threadpool(vault.remove, file["id"])
            except (SQLAlchemyError, OSError, ChatRequestError):
                logging.getLogger(__name__).warning(
                    "Chat attachment cleanup deferred to worker"
                )


@router.post("/conversations", status_code=202)
async def create(
    request: Request,
    prompt: Annotated[str, Form()],
    files: Annotated[list[UploadFile] | None, File()] = None,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    return await submit(request, None, prompt, files, [], idempotency_key)


@router.post("/conversations/{ident}/messages", status_code=202)
async def send(
    request: Request,
    ident: UUID,
    prompt: Annotated[str, Form()],
    files: Annotated[list[UploadFile] | None, File()] = None,
    attachment_ids: Annotated[list[UUID] | None, Form()] = None,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    return await submit(
        request, str(ident), prompt, files, attachment_ids, idempotency_key
    )


@router.get("/attachments/{ident}/download")
def download(request: Request, ident: UUID):
    file = store_for(request).attachment(owner(request), str(ident))
    data = FileVault(get_chat_settings()).read(file)
    return Response(
        data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(file['name'], safe='')}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/runs/{ident}")
def run(request: Request, ident: UUID):
    return store_for(request).run(owner(request), str(ident))


@router.post("/runs/{ident}/cancel", status_code=202)
def cancel(request: Request, ident: UUID):
    store_for(request).cancel(owner(request), str(ident))
    return {"cancel_requested": True}


def event(name, data, revision=None):
    prefix = f"id: {revision}\n" if revision is not None else ""
    return f"{prefix}event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


async def snapshots(request, ident, *, legacy=False):
    store, revision, content, checked = store_for(request), -1, "", 0.0
    try:
        while not await request.is_disconnected():
            if time.monotonic() - checked > 5:
                settings = request.app.state.identity_settings
                account = await run_in_threadpool(
                    request.app.state.identity_store.authenticate,
                    request.cookies.get(settings.cookie_name),
                )
                if account is None or account.user_id != owner(request):
                    yield event(
                        "error",
                        {
                            "error": {
                                "code": "authentication_required",
                                "message": "Please sign in again.",
                            }
                        },
                    )
                    return
                checked = time.monotonic()
            value = await run_in_threadpool(store.run, owner(request), ident)
            if value["revision"] != revision:
                revision = value["revision"]
                if legacy:
                    new_content = value["message"]["content"]
                    if new_content != content:
                        yield event(
                            "custom", {"response_delta": new_content[len(content) :]}
                        )
                        content = new_content
                    if value["status"] == "completed":
                        yield event("custom", {"response_complete": content})
                    elif value["status"] in TERMINAL:
                        yield event(
                            "error",
                            {
                                "error": {
                                    "code": value["error_code"] or "reply_stopped",
                                    "message": "The reply did not complete.",
                                }
                            },
                        )
                else:
                    yield event("snapshot", value, revision)
            if value["status"] in TERMINAL:
                return
            yield b": keepalive\n\n"
            await asyncio.sleep(0.5)
    except AccessError:
        yield event(
            "error",
            {"error": {"code": "not_found", "message": "Conversation unavailable."}},
        )


@router.get("/runs/{ident}/events")
async def stream(request: Request, ident: UUID):
    await run_in_threadpool(store_for(request).run, owner(request), str(ident))
    return StreamingResponse(
        snapshots(request, str(ident)),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
    )


async def legacy_stream(request, prompt, files, session_id):
    result = await submit(
        request,
        str(session_id) if session_id else None,
        prompt,
        files,
        [],
        request.headers.get("Idempotency-Key") or str(uuid4()),
    )

    async def body():
        yield event("metadata", result)
        async for chunk in snapshots(request, result["run_id"], legacy=True):
            yield chunk

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
    )

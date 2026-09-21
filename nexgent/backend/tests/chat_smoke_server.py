"""Opt-in browser fixture. Requires an explicitly disposable test database.

Run backend with --factory chat_smoke_server:backend and the deterministic
upstream with chat_smoke_server:agent (uvicorn --app-dir tests).
"""

import asyncio
import json
import os

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

agent = FastAPI()


@agent.post("/runs/stream")
async def stream(body: dict):
    value = body["input"]
    text = f"Reply to: {value['message']} | History: {len(value.get('history', []))} | Files: {len(value.get('attachments', []))}"

    async def chunks():
        for chunk in (text[:10], text[10:]):
            yield f"event: custom\ndata: {json.dumps({'response_delta': chunk})}\n\n"
            await asyncio.sleep(2 if "slow" in value["message"] else 0.2)
        yield f"event: custom\ndata: {json.dumps({'response_complete': text})}\n\n"

    return StreamingResponse(chunks(), media_type="text/event-stream")


@agent.get("/ok")
def health():
    return {"ok": True}


def backend():
    from app.identity.config import IdentitySettings
    from app.identity.models import ADMIN_ROLE_ID, User
    from app.identity.store import IdentityStore
    from app.main import create_app
    from sqlalchemy import select

    url = os.environ["NEXGENT_TEST_DATABASE_URL"]
    os.environ["NEXGENT_DATABASE_URL"] = url
    command.upgrade(Config("alembic.ini"), "head")
    settings = IdentitySettings(
        url,
        "http://127.0.0.1:58173",
        "disposable-browser-fixture-signing-key-only",
        False,
    )
    store = IdentityStore(settings)
    with store.sessions() as db:
        present = set(db.scalars(select(User.username)))
    for username in ("alice", "bob"):
        if username not in present:
            store.create_user(
                None,
                username=username,
                name=username.title(),
                email="",
                password="smoke-test",
                role_ids=[ADMIN_ROLE_ID] if username == "alice" else [],
                group_ids=[],
            )
    return create_app(identity_settings=settings, identity_store=store)

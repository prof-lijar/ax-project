import asyncio
import json
from contextlib import asynccontextmanager

import asyncpg
from ax_integrations.slack_files import verify_slack_signature
from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError

from workflows.sumin.events import normalize
from workflows.sumin.settings import Settings
from workflows.sumin.store import Store


def create_app(settings: Settings, store: Store, lifespan=None) -> FastAPI:
    @asynccontextmanager
    async def empty_lifespan(app):
        yield

    app = FastAPI(title="Sumin", lifespan=lifespan or empty_lifespan)

    @app.get("/healthz")
    async def health():
        return {"ok": True}

    @app.get("/readyz")
    async def ready():
        try:
            async with asyncio.timeout(2):
                await store.pool.fetchval("SELECT 1 FROM sumin.events LIMIT 1")
        except (asyncpg.PostgresError, OSError, TimeoutError):
            raise HTTPException(503, "sumin_not_ready") from None
        return {"ok": True}

    @app.post("/slack/events")
    async def events(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 1024 * 1024:
                raise HTTPException(413, "event_too_large")
        if not verify_slack_signature(
            bytes(body),
            request.headers.get("x-slack-request-timestamp", ""),
            request.headers.get("x-slack-signature", ""),
            settings.signing_secret,
        ):
            raise HTTPException(401, "invalid_slack_signature")
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise TypeError("invalid envelope")
            if payload.get("type") == "url_verification":
                challenge = payload.get("challenge")
                if not isinstance(challenge, str) or len(challenge) > 1000:
                    raise ValueError("invalid challenge")
                return {"challenge": challenge}
            tasks = normalize(payload, settings)
        except (ValueError, KeyError, TypeError, ValidationError):
            raise HTTPException(400, "invalid_slack_event") from None
        if tasks:
            try:
                # ACK only after commit, within Slack's 3-second delivery window.
                async with asyncio.timeout(2):
                    await store.enqueue(tasks)
            except (asyncpg.PostgresError, OSError, TimeoutError):
                raise HTTPException(503, "sumin_queue_unavailable") from None
        return {"ok": True}

    return app

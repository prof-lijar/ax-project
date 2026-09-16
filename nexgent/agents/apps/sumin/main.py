"""Run with uvicorn --factory; configuration is loaded at process startup only."""

import asyncio
from contextlib import asynccontextmanager

import asyncpg
import httpx
from ax_integrations.slack_files import SlackFiles

from workflows.sumin.settings import Settings
from workflows.sumin.store import Store

from .app import create_app


def create_application():
    settings = Settings.from_env()
    store = Store(None)

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(
            timeout=10, follow_redirects=False, trust_env=False
        ) as http:
            async with asyncio.timeout(15):
                app.state.settings = await settings.discover_identity(
                    SlackFiles(settings.bot_token, http)
                )
        async with asyncpg.create_pool(
            settings.database_dsn, min_size=1, max_size=4, command_timeout=10
        ) as pool:
            store.pool = pool
            await pool.fetchval("SELECT 1 FROM agent.sumin_events LIMIT 1")
            yield

    return create_app(settings, store, lifespan=lifespan)

"""Run with uvicorn --factory; configuration is loaded at process startup only."""

from contextlib import asynccontextmanager

import asyncpg

from workflows.sumin.settings import Settings
from workflows.sumin.store import Store

from .app import create_app


def create_application():
    settings = Settings.from_env()
    store = Store(None)

    @asynccontextmanager
    async def lifespan(app):
        async with asyncpg.create_pool(
            settings.database_dsn, min_size=1, max_size=4, command_timeout=10
        ) as pool:
            store.pool = pool
            await pool.fetchval("SELECT 1 FROM sumin.events LIMIT 1")
            yield

    return create_app(settings, store, lifespan=lifespan)

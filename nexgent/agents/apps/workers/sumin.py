"""Leased, bounded Sumin consumer; run as python -m apps.workers.sumin."""

import asyncio
import logging
import os
import ssl

import asyncpg
import httpx
from ax_contracts.sumin import SuminTask
from ax_integrations.file_http import FileIntegrationError
from ax_integrations.nextcloud import Nextcloud
from ax_integrations.slack_files import MemberSlackService, SlackFiles

from workflows.sumin.graph import build_graph
from workflows.sumin.service import Sumin
from workflows.sumin.settings import Settings
from workflows.sumin.store import Store

logger = logging.getLogger(__name__)


async def process_one(store: Store, graph) -> bool:
    row = await store.claim()
    if row is None:
        return False
    error = None
    try:
        if row["attempts"] > 5:
            raise FileIntegrationError("attempts_exhausted")
        task = SuminTask.model_validate_json(row["payload"])
        async with asyncio.timeout(300):
            await graph.ainvoke({"task": task.model_dump()}, {"recursion_limit": 3})
    except FileIntegrationError as exc:
        error = str(exc)
    except Exception:  # noqa: BLE001 - sanitize failures at the durable worker boundary
        error = "sumin_processing_failed"
    await store.finish(row, error)
    logger.info(
        "sumin_event_finished key=%s attempt=%s error=%s",
        row["key"],
        row["attempts"],
        error or "none",
        extra={
            "event_key": row["key"],
            "attempt": row["attempts"],
            "error_code": error,
        },
    )
    return True


async def run():
    # Sumin carries private upload text; inherited chat tracing must not export it.
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    settings = Settings.from_env()
    async with (
        asyncpg.create_pool(
            settings.database_dsn, min_size=1, max_size=4, command_timeout=10
        ) as pool,
        httpx.AsyncClient(
            timeout=60,
            follow_redirects=False,
            trust_env=False,
            limits=httpx.Limits(max_connections=4),
        ) as http,
        httpx.AsyncClient(
            timeout=60,
            follow_redirects=False,
            trust_env=False,
            limits=httpx.Limits(max_connections=4),
            verify=(
                ssl.create_default_context(cafile=settings.nextcloud_ca_bundle)
                if settings.nextcloud_verify_ssl
                else False
            ),
        ) as cloud_http,
    ):
        slack = SlackFiles(settings.bot_token, http)
        async with asyncio.timeout(15):
            settings = await settings.discover_identity(slack)
        store = Store(pool)
        service = Sumin(
            settings,
            store,
            slack,
            Nextcloud(
                settings.nextcloud_url,
                settings.nextcloud_user,
                settings.nextcloud_password,
                cloud_http,
            ),
            MemberSlackService(settings.bot_token, slack),
        )
        graph = build_graph(service)
        while True:
            try:
                if not await process_one(store, graph):
                    await asyncio.sleep(1)
            except (asyncpg.PostgresError, OSError, TimeoutError):
                logger.warning("sumin_queue_operation_failed")
                await asyncio.sleep(5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())

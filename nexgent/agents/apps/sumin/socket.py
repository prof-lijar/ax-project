"""Outbound Slack Socket Mode -> durable Sumin inbox; no public HTTP endpoint."""

import asyncio
import logging
import signal

import asyncpg
import httpx
from ax_integrations.slack_files import SlackFiles
from ax_integrations.slack_socket import SlackSocket

from workflows.sumin.events import normalize
from workflows.sumin.settings import Settings
from workflows.sumin.store import Store

logger = logging.getLogger(__name__)


def event_handler(settings: Settings, store: Store):
    async def handle(payload: dict):
        if settings.team_id is None:
            raise ValueError("Sumin identity is not initialized")
        tasks = normalize(payload, settings)
        if tasks:
            await store.enqueue(tasks)
            logger.info("sumin_event_queued count=%d", len(tasks))

    return handle


async def run():
    settings = Settings.from_env()
    if not settings.app_token.startswith("xapp-"):
        raise ValueError("SUMIN_SLACK_APP_TOKEN must be an xapp- token")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    async with (
        asyncpg.create_pool(
            settings.database_dsn, min_size=1, max_size=4, command_timeout=10
        ) as pool,
        httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False) as http,
    ):
        async with asyncio.timeout(15):
            settings = await settings.discover_identity(
                SlackFiles(settings.bot_token, http)
            )
        await pool.fetchval("SELECT 1 FROM agent.sumin_events LIMIT 1")
        socket = SlackSocket(
            settings.app_token, settings.bot_token, event_handler(settings, Store(pool))
        )
        await socket.run(stop)


def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        asyncio.run(run())
    except Exception:  # noqa: BLE001 - process boundary must not log credentials
        logger.error("sumin_socket_stopped_check_settings_and_connectivity")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

"""Run independently with python -m app.notifications.worker."""

import asyncio
import logging
import os
import random
import signal

import httpx
from sqlalchemy import create_engine
from starlette.concurrency import run_in_threadpool

from app.notifications.config import load_notification_settings
from app.notifications.slack import DeliveryError, SlackClient
from app.notifications.store import NotificationStore

logger = logging.getLogger("notifications.worker")


async def execute(store, sender, job, settings):
    try:
        # A removed/remapped destination revokes delivery of queued payloads.
        if settings.channels.get(job["destination"]) != job["channel_id"]:
            raise DeliveryError("notification_destination_changed")
        ts = await sender.send(job)
    except DeliveryError as error:
        delay = None
        if error.retryable and job["attempts"] < settings.max_attempts:
            delay = error.retry_after or min(300, 2 ** job["attempts"]) + random.uniform(0, 1)
        # Preserve the workspace cooldown even when this job exhausts retries.
        await run_in_threadpool(
            store.finish, job, error_code=error.code, retry_seconds=delay,
            cooldown_seconds=(error.retry_after or 60) if error.rate_limited else None,
        )
        logger.warning("Notification %s delivery error: %s", job["id"], error.code)
    else:
        await run_in_threadpool(store.finish, job, slack_ts=ts)
        logger.info("Notification %s sent", job["id"])


async def run_worker():
    settings = load_notification_settings()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    if not settings.enabled:
        logger.info("Slack notifications disabled; restart after configuring the environment")
        await stop.wait()
        return
    engine = create_engine(os.environ["NEXGENT_DATABASE_URL"], pool_pre_ping=True, hide_parameters=True)
    store = NotificationStore(engine, settings.deployment)
    tasks = set()
    try:
        await run_in_threadpool(store.ready)
        async with httpx.AsyncClient(
            limits=httpx.Limits(max_connections=settings.concurrency, max_keepalive_connections=settings.concurrency),
            follow_redirects=False,
        ) as client:
            sender = SlackClient(client, settings)
            try:
                while not stop.is_set():
                    for task in list(tasks):
                        if task.done():
                            tasks.remove(task)
                            if not task.cancelled() and task.exception():
                                # Do not log exception bodies or payloads/credentials.
                                logger.error("Notification execution interrupted; lease will recover")
                    try:
                        while len(tasks) < settings.concurrency and not stop.is_set():
                            job = await run_in_threadpool(store.claim, settings)
                            if not job:
                                break
                            tasks.add(asyncio.create_task(execute(store, sender, job, settings)))
                    except Exception:
                        logger.error("Notification queue unavailable; retrying")
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=settings.poll_seconds)
                    except TimeoutError:
                        pass
            finally:
                if tasks:
                    _, pending = await asyncio.wait(tasks, timeout=settings.timeout_seconds + 5)
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())

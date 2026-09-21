"""Run with python -m app.chat.worker; browser lifetime never owns generation."""

import asyncio
import json
import logging
import os
import signal
import time

from sqlalchemy import create_engine
from starlette.concurrency import run_in_threadpool

from app.chat.agent_server import open_agent_stream
from app.chat.config import get_chat_settings
from app.chat.store import ChatStore
from app.chat.vault import FileVault

logger = logging.getLogger("chat.worker")


async def events(response):
    event, data, length = "message", [], 0
    async for line in response.aiter_lines():
        length += len(line)
        if length > 2_000_000:
            raise ValueError("oversized stream event")
        if not line:
            if data:
                yield event, json.loads("\n".join(data))
            event, data, length = "message", [], 0
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())
    if data:
        yield event, json.loads("\n".join(data))


async def execute(store, vault, job, settings):
    ident, token = job["id"], job["token"]
    logger.info("Chat run %s started", ident)
    content, upstream, batch = "", None, None

    async def generate():
        nonlocal content, upstream, batch
        prompt, history, files = await run_in_threadpool(store.input, ident)
        batch = await run_in_threadpool(vault.stage, files)
        upstream = await open_agent_stream(
            prompt, batch.attachments, settings, history=history
        )
        completed, flushed = False, 0.0
        async for event, payload in events(upstream.response):
            if not isinstance(payload, dict):
                raise TypeError("invalid event")
            if event == "error" or "error" in payload:
                raise ValueError("agent failure")
            if event == "custom" or event.startswith("custom|"):
                if "response_delta" in payload:
                    if not isinstance(payload["response_delta"], str) or completed:
                        raise ValueError("invalid delta")
                    content += payload["response_delta"]
                    if len(content) > 1_000_000:
                        raise ValueError("response too large")
                if "response_complete" in payload:
                    final = payload["response_complete"]
                    if not isinstance(final, str) or not final or final != content:
                        raise ValueError("invalid completion")
                    completed = True
                if completed or time.monotonic() - flushed >= 0.25:
                    accepted = await run_in_threadpool(
                        store.output,
                        ident,
                        token,
                        content,
                        "completed" if completed else None,
                    )
                    if not accepted:
                        raise asyncio.CancelledError()
                    flushed = time.monotonic()
                if completed:
                    logger.info("Chat run %s completed", ident)
                    return
        if not completed:
            raise ValueError("incomplete stream")

    task = asyncio.create_task(generate())

    async def control():
        while not task.done():
            await asyncio.sleep(1)
            if not await run_in_threadpool(store.heartbeat, ident, token):
                task.cancel()
                return

    monitor = asyncio.create_task(control())
    try:
        async with asyncio.timeout(
            float(os.getenv("AX_CHAT_RUN_TIMEOUT_SECONDS", "300"))
        ):
            # Monitor failure must also stop a model call (e.g. database outage).
            done, _ = await asyncio.wait(
                [task, monitor], return_when=asyncio.FIRST_COMPLETED
            )
            if monitor in done:
                await monitor
            await task
    except asyncio.CancelledError:
        logger.info("Chat run %s stopped or interrupted", ident)
        await run_in_threadpool(
            store.output, ident, token, content, "interrupted", "worker_interrupted"
        )
        raise
    except Exception:  # noqa: BLE001 -- execution boundary; persist terminal failure
        logger.warning("Chat run %s failed", ident)
        try:
            await run_in_threadpool(
                store.output, ident, token, content, "failed", "generation_failed"
            )
        except Exception:  # noqa: BLE001 -- DB failure leaves lease for recovery
            logger.error("Chat output persistence unavailable", extra={"run_id": ident})
    finally:
        task.cancel()
        monitor.cancel()
        await asyncio.gather(task, monitor, return_exceptions=True)
        if upstream:
            await upstream.close()
        if batch:
            await batch.cleanup()


async def run_worker():
    settings = get_chat_settings()
    engine = create_engine(
        os.environ["NEXGENT_DATABASE_URL"], pool_pre_ping=True, hide_parameters=True
    )
    store, vault = ChatStore(engine), FileVault(settings)
    await run_in_threadpool(store.ready)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    tasks = set()
    concurrency = max(1, min(int(os.getenv("AX_CHAT_WORKER_CONCURRENCY", "4")), 32))
    maintenance_at = 0.0
    try:
        while not stop.is_set():
            for task in list(tasks):
                if task.done():
                    tasks.remove(task)
                    if not task.cancelled() and task.exception():
                        logger.error("Chat task interrupted before persistence")
            try:
                if time.monotonic() >= maintenance_at:
                    await run_in_threadpool(store.recover)
                    for ident, files in await run_in_threadpool(store.garbage):
                        for file in files:
                            await run_in_threadpool(vault.remove, file)
                        await run_in_threadpool(store.purge, ident)
                    await run_in_threadpool(vault.clean_orphans, store)
                    maintenance_at = time.monotonic() + 15
                while len(tasks) < concurrency:
                    job = await run_in_threadpool(store.claim)
                    if not job:
                        break
                    tasks.add(asyncio.create_task(execute(store, vault, job, settings)))
            except Exception:  # noqa: BLE001 -- keep the independent worker alive
                logger.error("Chat queue unavailable; retrying")
            try:
                await asyncio.wait_for(stop.wait(), timeout=1)
            except TimeoutError:
                pass
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())

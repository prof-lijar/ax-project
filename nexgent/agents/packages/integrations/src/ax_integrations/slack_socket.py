"""Bounded Socket Mode ingress. ACK only after the injected durable handler succeeds."""

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable

from slack_sdk.socket_mode.aiohttp import SocketModeClient
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.web.async_client import AsyncWebClient

from .file_http import FileIntegrationError

logger = logging.getLogger(__name__)


class _SafeTransportLog(logging.Filter):
    def filter(self, record):
        # SDK connection errors may contain credential-bearing WebSocket URLs.
        record.msg, record.args = "slack_socket_transport", ()
        record.exc_info = record.exc_text = None
        return True


class SlackSocket:
    def __init__(
        self,
        app_token: str,
        bot_token: str,
        handler: Callable[[dict], Awaitable[None]],
        *,
        client=None,
    ):
        if not app_token.startswith("xapp-"):
            raise ValueError("SUMIN_SLACK_APP_TOKEN must be an xapp- token")
        self.handler = handler
        self.active: set[asyncio.Task] = set()
        self.closing = False
        transport_log = logging.getLogger(__name__ + ".transport")
        if not transport_log.filters:
            transport_log.addFilter(_SafeTransportLog())
        self.client = client or SocketModeClient(
            app_token=app_token,
            web_client=AsyncWebClient(token=bot_token, timeout=10),
            logger=transport_log,
            trace_enabled=False,
        )
        self.client.message_queue = asyncio.Queue(maxsize=128)
        self.client.socket_mode_request_listeners.append(self.receive)

    async def receive(self, client, request):
        if self.closing or len(self.active) >= 4:
            logger.warning("slack_socket_ingress_busy")
            return  # No ACK: Slack may retry after backpressure subsides.
        current = asyncio.current_task()
        self.active.add(current)
        try:
            async with asyncio.timeout(2):
                if request.type == "events_api":
                    if len(json.dumps(request.payload).encode()) > 1024 * 1024:
                        raise FileIntegrationError("slack_event_too_large")
                    await self.handler(request.payload)
            async with asyncio.timeout(1):
                await client.send_socket_mode_response(
                    SocketModeResponse(envelope_id=request.envelope_id)
                )
        except Exception:  # noqa: BLE001 - never expose event content or SDK credentials
            logger.warning("slack_socket_event_unacknowledged")
        finally:
            self.active.discard(current)

    async def run(self, stop: asyncio.Event):
        disconnected_at = None
        try:
            async with asyncio.timeout(30):
                await self.client.connect()
            logger.info("slack_socket_connected")
            while not stop.is_set():
                if await self.client.is_connected():
                    disconnected_at = None
                elif disconnected_at is None:
                    disconnected_at = time.monotonic()
                elif time.monotonic() - disconnected_at > 60:
                    raise FileIntegrationError("slack_socket_reconnect_timeout")
                try:
                    await asyncio.wait_for(stop.wait(), timeout=5)
                except TimeoutError:
                    pass
        finally:
            self.closing = True
            try:
                async with asyncio.timeout(5):
                    await self.client.close()
            finally:
                pending = list(self.active)
                for task in pending:
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)

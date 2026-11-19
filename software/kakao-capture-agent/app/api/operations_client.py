"""Authenticated Nexgent device workflow. One execution attempt; no POST retries."""

import asyncio
import json
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID, uuid5

import httpx

from app.api.workflow_llm import check_cancel, validate_llm_url
from app.models import AgentError
from app.utils.windows import get_token

WORKFLOW_ID = "device_adjustment_power"
ASSISTANT_ID = str(uuid5(UUID("6ba7b821-9dad-11d1-80b4-00c04fd430c8"), "ax768_workflow"))


def credential_destination(url, username):
    return "operations:" + url.rstrip("/") + ":" + username.strip()


@dataclass(frozen=True)
class OperationsSettings:
    url: str
    username: str
    timeout: int = 435

    @classmethod
    def resolve(cls, config):
        url = config.operations_url.strip().rstrip("/")
        try:
            validate_llm_url(url, config.operations_allow_http)
        except ValueError:
            raise AgentError(
                "Set a valid Nexgent URL; enable trusted LAN HTTP only if needed"
            ) from None
        if urlsplit(url).path not in ("", "/"):
            raise AgentError("Use the Nexgent origin URL without an API path")
        if not config.operations_username.strip():
            raise AgentError("Set the Nexgent administrator username in Settings")
        return cls(url, config.operations_username.strip(), config.operations_timeout_seconds)


@dataclass(frozen=True)
class OperationsResult:
    status: str
    response: str
    completed: bool = False


def parse_result(body):
    if not isinstance(body, dict) or body.get("workflow_id") != WORKFLOW_ID:
        raise AgentError(
            "Operations API returned an invalid workflow result; inspect the operations sheet"
        )
    status, response = body.get("status"), body.get("response")
    if (
        not isinstance(status, str)
        or status
        not in {"completed", "disconnected", "not_found", "needs_confirmation", "blocked", "failed"}
        or not isinstance(response, str)
        or not response.strip()
    ):
        raise AgentError("Operations API result is incomplete; inspect the operations sheet")
    if status == "completed":
        signal, update, lookup, note = (
            body.get(k) for k in ("signal", "as_update", "as_lookup", "member_note")
        )
        if not all(isinstance(v, dict) for v in (signal, update, lookup, note)) or not (
            signal.get("status") == "connected"
            and signal.get("connected") is True
            and signal.get("fresh") is True
            and note.get("status") in ("saved", "already_present")
            and note.get("verified") is True
            and (
                (
                    lookup.get("status") == "found"
                    and update.get("status") == "updated"
                    and update.get("verified") is True
                )
                or (lookup.get("status") == "not_found" and update.get("status") == "skipped")
            )
        ):
            raise AgentError(
                "Operations API completion lacks verified receipts; inspect the operations sheet"
            )
    response = "".join(c for c in response if ord(c) >= 32 or c in "\n\t").strip()
    return OperationsResult(status, response[:900], status == "completed")


class OperationsClient:
    def __init__(self, settings, password, transport=None):
        if not password:
            raise AgentError("Save the Nexgent password in Settings or set OPERATIONS_PASSWORD")
        self.settings, self.password, self.transport = settings, password, transport

    async def request(self, client, method, path, **kwargs):
        async with client.stream(method, self.settings.url + path, **kwargs) as response:
            if not 200 <= response.status_code < 300:
                raise AgentError(f"Operations API HTTP {response.status_code}; no automatic retry")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > 1_000_000:
                    raise AgentError(
                        "Operations API response exceeds limit; inspect the operations sheet"
                    )
        try:
            return json.loads(body)
        except ValueError:
            raise AgentError(
                "Operations API returned invalid JSON; inspect the operations sheet"
            ) from None

    async def execute(self, message, cancel):
        async with httpx.AsyncClient(
            timeout=self.settings.timeout,
            transport=self.transport,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            origin = {"Origin": self.settings.url}
            check_cancel(cancel)
            await self.request(
                client,
                "POST",
                "/auth/login",
                headers=origin,
                json={"username": self.settings.username, "password": self.password},
            )
            check_cancel(cancel)
            account = await self.request(client, "GET", "/api/me")
            if (
                not isinstance(account, dict)
                or account.get("is_admin") is not True
                or not isinstance(account.get("csrf_token"), str)
                or not account["csrf_token"]
            ):
                raise AgentError("Nexgent administrator access and CSRF token are required")
            check_cancel(cancel)
            schema = await self.request(
                client, "GET", f"/agent-server/assistants/{ASSISTANT_ID}/schemas"
            )
            try:
                mode = schema["input_schema"]["properties"]["member_note_mode"]["const"]
            except (KeyError, TypeError):
                mode = None
            if mode != "append":
                raise AgentError(
                    "Update/rebuild Nexgent Agent Server to enable appending general notes; no workflow executed"
                )
            check_cancel(cancel)
            body = await self.request(
                client,
                "POST",
                "/api/ax768/workflow/runs",
                headers={**origin, "X-CSRF-Token": account["csrf_token"]},
                json={"workflow_id": WORKFLOW_ID, "message": message, "confirmed_name": None},
            )
            return parse_result(body)

    async def run_async(self, message, cancel):
        check_cancel(cancel)
        task = asyncio.create_task(self.execute(message, cancel))
        try:
            async with asyncio.timeout(self.settings.timeout):
                while not task.done():
                    check_cancel(cancel)
                    await asyncio.wait({task}, timeout=0.1)
                check_cancel(cancel)
                return task.result()
        except (httpx.RequestError, TimeoutError):
            raise AgentError(
                "Operations API connection failed or timed out; result uncertain, no automatic retry"
            ) from None
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    def run(self, message, cancel):
        return asyncio.run(self.run_async(message, cancel))


def create_operations(config):
    settings = OperationsSettings.resolve(config)
    return OperationsClient(
        settings,
        get_token(credential_destination(settings.url, settings.username), "OPERATIONS_PASSWORD"),
    )

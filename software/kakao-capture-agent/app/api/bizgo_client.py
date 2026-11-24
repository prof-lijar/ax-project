"""Bizgo v2 Omni: one SMS/LMS recipient, one attempt, explicit acceptance status."""

import asyncio
import json
import re
from dataclasses import dataclass, field

import httpx

from app.models import AgentError, Cancelled
from app.utils.windows import get_token

BIZGO_CREDENTIAL = "bizgo:v2:api-key"
BIZGO_SAMPLE = "[test] Kakao Capture Agent Bizgo SMS test."
SEND_PATH = "/api/comm/v1/send/omni"
BASE_URLS = {
    True: "https://sandbox-mars.ibapi.kr",
    False: "https://mars.ibapi.kr",
}


def phone_number(value):
    if not isinstance(value, str):
        raise ValueError("Bizgo phone numbers must be text")
    number = re.sub(r"[ ()-]", "", value)
    if not re.fullmatch(r"[0-9]{8,15}", number):
        raise ValueError("Bizgo sender and recipient need 8–15 digits, including the area code")
    return number


def installation_test_numbers(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Enter the installation test recipient numbers in Bizgo settings")
    return list(dict.fromkeys(phone_number(part.strip()) for part in value.split(",")))


def validate_bizgo_config(config):
    if config.bizgo_installation_test or config.bizgo_test_recipients:
        installation_test_numbers(config.bizgo_test_recipients)
    for value in (config.bizgo_sender, config.bizgo_recipient):
        if value or config.bizgo_enabled:
            phone_number(value)


@dataclass(frozen=True)
class BizgoSettings:
    sender: str = field(repr=False)
    recipient: str = field(repr=False)
    sandbox: bool = True
    timeout: int = 15

    @classmethod
    def resolve(cls, config):
        try:
            return cls(
                phone_number(config.bizgo_sender),
                phone_number(config.bizgo_recipient),
                config.bizgo_sandbox,
                config.bizgo_timeout_seconds,
            )
        except ValueError as error:
            raise AgentError(str(error)) from None

    @property
    def url(self):
        return BASE_URLS[self.sandbox] + SEND_PATH


@dataclass(frozen=True)
class PreparedMessage:
    payload: dict = field(repr=False)
    channel: str
    warnings: tuple[str, ...]


def phone_text(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 10000:
        raise AgentError("Bizgo message is empty or exceeds the local size limit")
    if any(ord(c) < 32 and c not in "\n\r\t" for c in text):
        raise AgentError("Bizgo message contains unsupported control characters")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Domestic carriers measure EUC-KR bytes. Make changes explicit instead of
    # relying on the carrier to silently corrupt emoji or truncate a long reply.
    normalized = text.encode("euc-kr", errors="replace").decode("euc-kr")
    warnings = []
    if normalized != text:
        warnings.append(
            "Bizgo copy: characters unsupported by domestic SMS/LMS were replaced with ?"
        )
    if len(normalized.encode("euc-kr")) > 2000:
        suffix = "\n[Shortened for LMS; full text in KakaoTalk]"
        budget = 2000 - len(suffix.encode("euc-kr"))
        prefix = []
        for char in normalized:
            size = len(char.encode("euc-kr"))
            if size > budget:
                break
            prefix.append(char)
            budget -= size
        normalized = "".join(prefix) + suffix
        warnings.append(
            "Bizgo copy shortened to the 2,000-byte LMS limit; KakaoTalk keeps the full reply"
        )
    return normalized, tuple(warnings)


def safe_code(value):
    return value if isinstance(value, str) and re.fullmatch(r"[A-Z][0-9]{3}", value) else "unknown"


class BizgoClient:
    def __init__(self, settings, token, audit, transport=None):
        if not token or any(ord(c) < 33 or ord(c) > 126 for c in token):
            raise AgentError("Configure a valid Bizgo API key in Settings or BIZGO_API_KEY")
        self.settings, self.token, self.audit, self.transport = settings, token, audit, transport

    def prepare(self, reply, capture_id):
        text, warnings = phone_text(reply)
        channel = "SMS" if len(text.encode("euc-kr")) <= 90 else "LMS"
        return self._prepare(text, "[test] Workflow summary", capture_id, channel, warnings)

    def prepare_installation(self, title, text, reference):
        if not title.strip() or not text.strip() or any(
            ord(c) < 32 and c not in "\n\r\t" for c in text
        ) or any(ord(c) < 32 for c in title):
            raise AgentError("Invalid installation guide text or title")
        # Preserve the API guide in full, even when it spans multiple LMS messages.
        parts, start, size = [], 0, 0
        for index, char in enumerate(text):
            try:
                width = len(char.encode("euc-kr"))
            except UnicodeEncodeError:
                raise AgentError("Installation guide contains a character unsupported by LMS") from None
            if size + width > 2000:
                parts.append(text[start:index])
                start, size = index, 0
            size += width
        parts.append(text[start:])
        return [self._prepare(part, title, f"{reference}-{i}", "LMS", ())
                for i, part in enumerate(parts)]

    def _prepare(self, text, title, capture_id, channel, warnings):
        if not re.fullmatch(r"[A-Za-z0-9-]{1,100}", capture_id):
            raise AgentError("Invalid workflow reference for Bizgo")
        content = {"from": self.settings.sender, "text": text}
        if channel == "LMS":
            content["title"] = title
        payload = {
            "destinations": [{"to": self.settings.recipient}],
            "messageFlow": [{"sms" if channel == "SMS" else "mms": content}],
            "ref": capture_id,
            "idempotencyKey": capture_id,
            "idempotencyTtl": 86400,
        }
        return PreparedMessage(payload, channel, warnings)

    def acknowledgement(self, response, message):
        try:
            body = json.loads(response)
            auth = body["common"]["authCode"]
            if auth != "A000":
                raise AgentError(
                    f"Bizgo authentication rejected ({safe_code(auth)}); check key and allowed public IP"
                )
            service = body["data"]
            if service["code"] != "A000":
                raise AgentError(
                    f"Bizgo request rejected ({safe_code(service['code'])}); no automatic retry"
                )
            destinations = service["data"]["destinations"]
            if not isinstance(destinations, list) or len(destinations) != 1:
                raise ValueError()
            recipient = destinations[0]
            if (
                service.get("ref") != message.payload["ref"]
                or recipient["to"] != self.settings.recipient
            ):
                raise ValueError()
            if recipient["code"] != "A000":
                raise AgentError(
                    f"Bizgo recipient rejected ({safe_code(recipient['code'])}); no automatic retry"
                )
            key = recipient["msgKey"]
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", key):
                raise ValueError()
            return key
        except (ValueError, KeyError, IndexError, TypeError):
            raise AgentError(
                "Bizgo acknowledgement is invalid; outcome uncertain, no automatic retry"
            ) from None

    async def post(self, message):
        async with httpx.AsyncClient(
            timeout=self.settings.timeout,
            follow_redirects=False,
            trust_env=False,
            transport=self.transport,
        ) as client:
            async with client.stream(
                "POST",
                self.settings.url,
                headers={"Authorization": self.token},
                json=message.payload,
            ) as response:
                if not 200 <= response.status_code < 300:
                    uncertain = response.status_code >= 500
                    raise AgentError(
                        f"Bizgo HTTP {response.status_code}; "
                        + ("outcome uncertain" if uncertain else "request not accepted")
                        + ", no automatic retry"
                    )
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 64 * 1024:
                        raise AgentError(
                            "Bizgo response too large; outcome uncertain, no automatic retry"
                        )
                return self.acknowledgement(body, message)

    async def send_async(self, message, cancel):
        if cancel.is_set():
            raise Cancelled("Stopped before Bizgo request; no phone message requested")
        reference = message.payload["ref"]
        mode = "sandbox" if self.settings.sandbox else "production"
        self.audit(
            "bizgo_attempt",
            json.dumps({"capture_id": reference, "environment": mode, "channel": message.channel}),
        )
        if cancel.is_set():
            raise Cancelled("Stopped before Bizgo request; no phone message requested")
        task = asyncio.create_task(self.post(message))
        try:
            async with asyncio.timeout(self.settings.timeout):
                while not task.done():
                    if cancel.is_set():
                        raise Cancelled(
                            "Stopped during Bizgo request; it may already be accepted, no automatic retry"
                        )
                    await asyncio.wait({task}, timeout=0.1)
                key = task.result()
            self.audit(
                "bizgo_accepted",
                json.dumps(
                    {
                        "capture_id": reference,
                        "environment": mode,
                        "channel": message.channel,
                        "msg_key": key,
                    }
                ),
            )
            return (
                f"Bizgo sandbox accepted {message.channel} test; no real message delivered"
                if self.settings.sandbox
                else f"Bizgo accepted {message.channel}; final delivery pending (check Bizgo reports)"
            )
        except (httpx.RequestError, TimeoutError):
            self.audit("bizgo_uncertain", reference + ": connection failed or timed out")
            raise AgentError(
                "Bizgo connection failed or timed out; outcome uncertain, no automatic retry"
            ) from None
        except AgentError as error:
            self.audit("bizgo_incomplete", reference + ": " + str(error))
            raise
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    def send(self, message, cancel):
        return asyncio.run(self.send_async(message, cancel))


def create_bizgo(config, audit, *, force=False):
    if not config.bizgo_enabled and not force:
        return None
    return BizgoClient(
        BizgoSettings.resolve(config), get_token(BIZGO_CREDENTIAL, "BIZGO_API_KEY"), audit
    )

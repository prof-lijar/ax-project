import asyncio
import hashlib
import hmac
import json
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from ax_contracts.sumin import SuminTask
from ax_integrations.file_http import FileIntegrationError
from ax_integrations.nextcloud import CloudFile, Nextcloud, path_component
from ax_integrations.slack_files import (
    SlackFiles,
    verify_slack_signature,
)
from pydantic import ValidationError

from apps.sumin.app import create_app
from apps.workers.sumin import process_one
from workflows.sumin.events import normalize
from workflows.sumin.graph import build_graph
from workflows.sumin.service import Sumin, search_terms
from workflows.sumin.settings import Settings

CHANNEL = "C12345678"
TEAM = "T12345678"


@pytest.fixture
def settings():
    return Settings(
        team_id=TEAM,
        bot_user_id="U12345678",
        channels=frozenset({CHANNEL}),
        bot_token="xoxb-test",
        signing_secret="test-secret",
        database_dsn="postgresql://unused",
        nextcloud_url="https://cloud.example/nextcloud",
        nextcloud_user="sumin",
        nextcloud_password="test-password",
    )


def task(**overrides):
    values = {
        "event_id": "Ev123",
        "team_id": TEAM,
        "channel_id": CHANNEL,
        "kind": "archive",
        "file_id": "F12345678",
        "message_ts": "123456.123",
        "text": "Quarterly budget review",
    }
    values.update(overrides)
    return SuminTask(**values)


def envelope(**event):
    return {
        "type": "event_callback",
        "team_id": TEAM,
        "event_id": "Ev123",
        "event": {
            "type": "message",
            "channel": CHANNEL,
            "ts": "123456.123",
            "user": "UOTHER",
            "text": "Budget discussion",
            "files": [{"id": "F12345678"}],
            **event,
        },
    }


def signed(payload, *, timestamp=None):
    body = json.dumps(payload).encode()
    timestamp = str(int(time.time())) if timestamp is None else str(timestamp)
    signature = (
        "v0="
        + hmac.new(
            b"test-secret", b"v0:" + timestamp.encode() + b":" + body, hashlib.sha256
        ).hexdigest()
    )
    return body, {
        "x-slack-signature": signature,
        "x-slack-request-timestamp": timestamp,
        "content-type": "application/json",
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "archive", "file_id": None},
        {"file_id": "../../secret"},
        {"kind": "search", "file_id": None, "message_ts": None},
        {"unknown": "bad"},
        {"team_id": 123},
    ],
)
def test_contract_rejects_invalid_tasks(overrides):
    with pytest.raises(ValidationError):
        task(**overrides)


def test_normalizes_modern_messages_file_shared_and_mentions(settings):
    assert normalize(envelope(), settings)[0].text == "Budget discussion"
    shared = envelope(type="file_shared", file_id="F12345678")
    shared["event"]["channel_id"] = shared["event"].pop("channel")
    assert normalize(shared, settings)[0].file_id == "F12345678"
    mention = normalize(
        envelope(type="app_mention", text="<@U12345678> budget"), settings
    )[0]
    assert mention.kind == "search" and mention.file_id is None


@pytest.mark.parametrize(
    "event",
    [
        {"channel": "COTHER123"},
        {"channel": "D12345678"},
        {"bot_id": "B123"},
        {"user": "U12345678"},
        {"subtype": "message_changed"},
        {"type": "reaction_added"},
    ],
)
def test_ignores_unauthorized_or_irrelevant_events(settings, event):
    assert normalize(envelope(**event), settings) == []


def test_ignores_other_workspace(settings):
    payload = envelope()
    payload["team_id"] = "TOTHER"
    assert normalize(payload, settings) == []


@pytest.mark.asyncio
async def test_signed_ingress_commits_before_ack_and_handles_verification(settings):
    store = SimpleNamespace(enqueue=AsyncMock())
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings, store)),
        base_url="http://test",
    )
    body, headers = signed(envelope())
    assert (
        await client.post("/slack/events", content=body, headers=headers)
    ).status_code == 200
    assert store.enqueue.await_count == 1
    assert (
        await client.post("/slack/events", content=body + b" ", headers=headers)
    ).status_code == 401
    old_body, old_headers = signed(envelope(), timestamp=int(time.time()) - 600)
    assert (
        await client.post("/slack/events", content=old_body, headers=old_headers)
    ).status_code == 401
    store.enqueue.side_effect = OSError("private infrastructure detail")
    response = await client.post("/slack/events", content=body, headers=headers)
    assert response.status_code == 503 and "private" not in response.text
    body, headers = signed({"type": "url_verification", "challenge": "challenge"})
    assert (
        await client.post("/slack/events", content=body, headers=headers)
    ).json() == {"challenge": "challenge"}


@pytest.mark.asyncio
async def test_invalid_and_oversized_ingress(settings):
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=create_app(settings, SimpleNamespace(enqueue=AsyncMock()))
        ),
        base_url="http://test",
    )
    body, headers = signed({"type": "event_callback", "team_id": TEAM, "event": []})
    assert (
        await client.post("/slack/events", content=body, headers=headers)
    ).status_code == 400
    assert (
        await client.post("/slack/events", content=b"x" * (1024 * 1024 + 1))
    ).status_code == 413
    assert not verify_slack_signature(b"", "bad", "bad", "secret")


class FakeStore:
    def __init__(self):
        self.folders, self.paths, self.contexts = {}, {}, {}

    async def folder(self, team, channel, proposed):
        return self.folders.setdefault((team, channel), proposed)

    async def file_path(self, work, proposed):
        return self.paths.setdefault(
            (work.team_id, work.channel_id, work.file_id), proposed
        )

    async def save_context(self, work):
        self.contexts[work.key] = work

    async def match_context(self, work, terms):
        return {
            c.file_id
            for c in self.contexts.values()
            if c.team_id == work.team_id
            and c.channel_id == work.channel_id
            and any(t in c.text.casefold() for t in terms)
        }


class FakeCloud:
    def __init__(self):
        self.data, self.folders = {}, set()
        self.fail_context = False

    async def mkdirs(self, folder):
        self.folders.add(folder)

    async def put_once(self, path, data):
        if self.fail_context and path.endswith(".json"):
            self.fail_context = False
            raise FileIntegrationError("nextcloud_upload_failed")
        if path in self.data and self.data[path] != data:
            raise FileIntegrationError("nextcloud_file_conflict")
        self.data[path] = data

    async def list_files(self, folder):
        return [
            CloudFile(path.rsplit("/", 1)[1], f"https://cloud.example/index.php/f/{i}")
            for i, path in enumerate(self.data, 1)
            if path.startswith(folder + "/") and "/" not in path[len(folder) + 1 :]
        ]


def service(settings):
    slack = SimpleNamespace(info=AsyncMock(), download=AsyncMock(return_value=b"abc"))

    async def info(method, **kwargs):
        if method == "conversations.info":
            return {"channel": {"id": CHANNEL, "name": "finance", "is_member": True}}
        return {
            "file": {
                "id": "F12345678",
                "mode": "hosted",
                "size": 3,
                "name": "plan.pdf",
                "url_private_download": "https://files.slack.com/test",
            }
        }

    slack.info.side_effect = info
    return Sumin(
        settings,
        FakeStore(),
        slack,
        FakeCloud(),
        SimpleNamespace(
            send_message=AsyncMock(return_value=SimpleNamespace(success=True))
        ),
    )


@pytest.mark.asyncio
async def test_archive_resume_duplicate_and_context_search_graph(settings):
    agent = service(settings)
    graph = build_graph(agent)
    agent.cloud.fail_context = True
    with pytest.raises(FileIntegrationError):
        await graph.ainvoke({"task": task().model_dump()})
    assert len(agent.cloud.data) == 1  # File committed, context pending.
    for _ in range(2):
        result = await graph.ainvoke({"task": task().model_dump()})
        assert result["result"] == "archived"
    assert len(agent.cloud.data) == 2  # Replays did not create more files.
    assert f"Slack/{TEAM}/finance/F12345678--plan.pdf" in agent.cloud.data
    context = json.loads(
        next(v for k, v in agent.cloud.data.items() if k.endswith(".json"))
    )
    assert context["text"] == "Quarterly budget review"
    assert context["message_ts"] == "123456.123"
    search = task(
        event_id="EvSearch",
        kind="search",
        file_id=None,
        text="<@U12345678> please find budget files",
        thread_ts="123000.100",
    )
    await graph.ainvoke({"task": search.model_dump()})
    message = agent.sender.send_message.call_args.args[0]
    assert message.channel_id == CHANNEL and message.thread_ts == "123000.100"
    assert "https://cloud.example/index.php/f/1" in message.text
    assert ".json" not in message.text
    # Deleted files are not returned just because their upload context remains indexed.
    agent.cloud.data.clear()
    await agent.run(search)
    assert "couldn’t find" in agent.sender.send_message.call_args.args[0].text


@pytest.mark.asyncio
async def test_authority_rechecked_and_channel_mapping_stable(settings):
    agent = service(settings)
    with pytest.raises(FileIntegrationError, match="channel_not_authorized"):
        await agent.run(task(channel_id="COTHER123"))
    agent.slack.info.assert_not_called()
    first = await agent.store.folder(TEAM, CHANNEL, "Slack/finance")
    assert await agent.store.folder(TEAM, CHANNEL, "Slack/new-name") == first


@pytest.mark.asyncio
async def test_size_limit_no_cloud_write_and_no_bare_mention_listing(settings):
    agent = service(replace(settings, max_file_bytes=2))
    with pytest.raises(FileIntegrationError, match="file_too_large"):
        await agent.run(task())
    assert agent.cloud.data == {}
    agent.slack.download.assert_not_called()
    await agent.run(task(kind="search", file_id=None, text="<@U12345678> find files"))
    assert "Tell me a filename" in agent.sender.send_message.call_args.args[0].text


@pytest.mark.asyncio
async def test_worker_retries_sanitizes_failures_and_propagates_cancellation():
    row = {"payload": task().model_dump_json(), "attempts": 1, "key": task().key}
    store = SimpleNamespace(claim=AsyncMock(return_value=row), finish=AsyncMock())
    graph = SimpleNamespace(
        ainvoke=AsyncMock(side_effect=RuntimeError("secret provider body"))
    )
    assert await process_one(store, graph)
    assert store.finish.call_args.args[1] == "sumin_processing_failed"
    store.finish.reset_mock()
    graph.ainvoke.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await process_one(store, graph)
    store.finish.assert_not_called()  # Lease expiry owns interrupted work recovery.
    row["attempts"] = 6
    assert await process_one(store, graph)
    assert store.finish.call_args.args[1] == "attempts_exhausted"


def test_search_terms_and_safe_names():
    assert search_terms('<@U123> Please find "Q3 budget.xlsx"') == ["q3 budget.xlsx"]
    assert search_terms("<@U123> 예산 파일 찾아줘") == ["예산"]
    assert search_terms("find files please") == []
    assert "/" not in path_component("../../unsafe\\file.pdf")
    assert len(path_component("가" * 100).encode()) <= 160


@pytest.mark.asyncio
async def test_slack_download_origin_redirect_and_size_guards():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(302, headers={"location": "https://evil.example/file"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        slack = SlackFiles("xoxb-secret", http)
        for url in [
            "https://evil.example/a",
            "http://files.slack.com/a",
            "https://files.slack.com.evil/a",
        ]:
            with pytest.raises(FileIntegrationError, match="unsafe_slack_download"):
                await slack.download(url, 3)
        assert seen == []
        with pytest.raises(FileIntegrationError, match="slack_download_failed"):
            await slack.download("https://files.slack.com/a", 3)
        assert (
            len(seen) == 1 and seen[0].headers["authorization"] == "Bearer xoxb-secret"
        )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"abcd"))
    ) as http:
        with pytest.raises(FileIntegrationError, match="response_too_large"):
            await SlackFiles("xoxb-secret", http).download(
                "https://files.slack.com/a", 3
            )


@pytest.mark.asyncio
async def test_nextcloud_conditional_upload_replay_and_conflict():
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "PUT":
            assert request.headers["if-none-match"] == "*"
            return httpx.Response(412)
        return httpx.Response(200, content=b"abc")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        cloud = Nextcloud("https://cloud.example", "sumin", "secret", http)
        await cloud.put_once("Slack/file.txt", b"abc")
        with pytest.raises(FileIntegrationError, match="nextcloud_file_conflict"):
            await cloud.put_once("Slack/file.txt", b"xyz")
        with pytest.raises(ValueError):
            cloud.url("../secret")
    assert all(r.url.host == "cloud.example" for r in requests)


@pytest.mark.asyncio
async def test_webdav_filters_outside_scope_collections_and_failed_properties():
    prefix = "/nextcloud/remote.php/dav/files/sumin/Slack/finance/"

    def entry(href, file_id, status="200 OK", collection=False):
        return f"<d:response><d:href>{href}</d:href><d:propstat><d:prop><oc:fileid>{file_id}</oc:fileid><d:resourcetype>{'<d:collection/>' if collection else ''}</d:resourcetype></d:prop><d:status>HTTP/1.1 {status}</d:status></d:propstat></d:response>"

    body = (
        '<d:multistatus xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">'
        + entry(prefix + "F1--Budget%20%26%20plan.pdf", "42")
        + entry(prefix + "folder/", "43", collection=True)
        + entry(prefix + "secret.pdf", "44", "403 Forbidden")
        + entry("/different-channel/private.pdf", "45")
        + entry("https://evil.example" + prefix + "file.pdf", "46")
        + "</d:multistatus>"
    ).encode()

    def handler(request):
        assert request.method == "PROPFIND" and request.headers["depth"] == "1"
        return httpx.Response(207, content=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        cloud = Nextcloud("https://cloud.example/nextcloud", "sumin", "secret", http)
        assert await cloud.list_files("Slack/finance") == [
            CloudFile(
                "F1--Budget & plan.pdf",
                "https://cloud.example/nextcloud/index.php/f/42",
            )
        ]


@pytest.mark.asyncio
async def test_webdav_refuses_xml_entities():
    xml = b'<!DOCTYPE foo [<!ENTITY x "boom">]><foo>&x;</foo>'
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(207, content=xml))
    ) as http:
        cloud = Nextcloud("https://cloud.example", "sumin", "secret", http)
        with pytest.raises(FileIntegrationError):
            await cloud.list_files("Slack")


def test_env_configuration_isolated_from_existing_slack_settings(settings, monkeypatch):
    values = {
        "SLACK_TEAM_ID": TEAM,
        "SLACK_BOT_USER_ID": "U12345678",
        "SLACK_CHANNEL_IDS": CHANNEL,
        "SLACK_BOT_TOKEN": "xoxb-test",
        "SLACK_SIGNING_SECRET": "secret",
        "DATABASE_DSN": "postgresql://unused",
        "NEXTCLOUD_URL": "https://cloud.example",
        "NEXTCLOUD_USER": "sumin",
        "NEXTCLOUD_PASSWORD": "secret",
    }
    for key, value in values.items():
        monkeypatch.setenv("SUMIN_" + key, value)
    monkeypatch.setenv("SLACK_BOT_TOKEN", "unrelated-token")
    assert Settings.from_env().bot_token == "xoxb-test"
    monkeypatch.setenv("SUMIN_SLACK_CHANNEL_IDS", "")
    with pytest.raises(ValueError, match="SUMIN_SLACK_CHANNEL_IDS"):
        Settings.from_env()


@pytest.mark.asyncio
@pytest.mark.parametrize("collection", [True, False])
async def test_existing_nextcloud_folder_verified_before_upload(collection):
    def handler(request):
        if request.method == "MKCOL":
            return httpx.Response(405)
        body = (
            '<d:multistatus xmlns:d="DAV:"><d:response><d:propstat><d:prop>'
            "<d:resourcetype>"
            + ("<d:collection/>" if collection else "")
            + "</d:resourcetype></d:prop></d:propstat></d:response></d:multistatus>"
        )
        return httpx.Response(207, text=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        cloud = Nextcloud("https://cloud.example", "sumin", "secret", http)
        if collection:
            await cloud.mkdirs("Slack/finance")
        else:
            with pytest.raises(FileIntegrationError, match="nextcloud_folder_conflict"):
                await cloud.mkdirs("Slack/finance")


@pytest.mark.asyncio
async def test_failed_slack_reply_does_not_complete_task(settings):
    agent = service(settings)
    agent.sender.send_message.return_value.success = False
    with pytest.raises(FileIntegrationError, match="slack_reply_failed"):
        await agent.run(task(kind="search", file_id=None, text="budget"))


@pytest.mark.asyncio
async def test_channel_membership_revocation_stops_collection(settings):
    agent = service(settings)
    agent.slack.info.side_effect = None
    agent.slack.info.return_value = {
        "channel": {"id": CHANNEL, "name": "finance", "is_member": False}
    }
    with pytest.raises(FileIntegrationError, match="bot_not_channel_member"):
        await agent.run(task())
    agent.slack.download.assert_not_called()
    assert agent.cloud.data == {}


def test_uploads_attached_to_mentions_are_also_collected(settings):
    tasks = normalize(
        envelope(type="app_mention", text="<@U12345678> find budget"), settings
    )
    assert [task.kind for task in tasks] == ["search", "archive"]
    assert len({task.key for task in tasks}) == 2

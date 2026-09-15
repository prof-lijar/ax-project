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
            return {
                "channel": {
                    "id": kwargs["channel"],
                    "name": "finance"
                    if kwargs["channel"] == CHANNEL
                    else kwargs["channel"].lower(),
                    "is_member": True,
                }
            }
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
    slack.member_channel = lambda channel: SlackFiles.member_channel(slack, channel)
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
@pytest.mark.parametrize("mode", ["hosted", "snippet"])
@pytest.mark.parametrize("download_field", ["url_private_download", "url_private"])
async def test_markdown_archive_preserves_bytes_and_replays(
    settings, mode, download_field
):
    agent = service(settings)
    original_info = agent.slack.info.side_effect
    content = "# Notes\n\n한글 **Markdown**\n".encode()

    async def info(method, **kwargs):
        result = await original_info(method, **kwargs)
        if method == "files.info":
            result["file"] = {
                "id": "F12345678",
                "mode": mode,
                "is_external": False,
                "size": len(content),
                "name": "notes.md",
                download_field: "https://files.slack.com/test",
                "preview": "truncated preview must not be archived",
            }
        return result

    agent.slack.info.side_effect = info
    agent.slack.download.return_value = content
    graph = build_graph(agent)
    for _ in range(2):
        result = await graph.ainvoke({"task": task().model_dump()})
        assert result["result"] == "archived"
    assert agent.cloud.data["Slack/finance/F12345678--notes.md"] == content
    assert len(agent.cloud.data) == 2
    agent.slack.download.assert_awaited_with(
        "https://files.slack.com/test", settings.max_file_bytes
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metadata",
    [
        {"mode": "external"},
        {"mode": "post"},
        {"mode": None},
        {"mode": "unknown"},
        {"mode": "snippet", "is_external": True},
        {"mode": "snippet", "id": "F99999999"},
    ],
)
async def test_archive_rejects_unsupported_file_metadata(settings, metadata):
    agent = service(settings)
    original_info = agent.slack.info.side_effect

    async def info(method, **kwargs):
        result = await original_info(method, **kwargs)
        if method == "files.info":
            result["file"].update(metadata)
        return result

    agent.slack.info.side_effect = info
    with pytest.raises(FileIntegrationError, match="unsupported_slack_file"):
        await agent.run(task())
    agent.slack.download.assert_not_awaited()
    assert not agent.cloud.data


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
    assert "Slack/finance/F12345678--plan.pdf" in agent.cloud.data
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
        await agent.run(task(team_id="TOTHER123"))
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
        "SLACK_BOT_TOKEN": "xoxb-test",
        "SLACK_SIGNING_SECRET": "secret",
        "NEXTCLOUD_URL": "https://cloud.example",
        "NEXTCLOUD_USER": "sumin",
        "NEXTCLOUD_PASSWORD": "secret",
    }
    for key, value in values.items():
        monkeypatch.setenv("SUMIN_" + key, value)
    monkeypatch.setenv("AGENT_DATABASE_DSN", "postgresql://shared-agent-database")
    monkeypatch.setenv("SUMIN_DATABASE_DSN", "postgresql://obsolete-database")
    assert Settings.from_env().database_dsn == "postgresql://shared-agent-database"
    monkeypatch.setenv("SLACK_BOT_TOKEN", "unrelated-token")
    assert Settings.from_env().bot_token == "xoxb-test"
    assert Settings.from_env().team_id is None
    for key in ("SLACK_TEAM_ID", "SLACK_BOT_USER_ID", "SLACK_CHANNEL_IDS"):
        monkeypatch.setenv("SUMIN_" + key, "obsolete-value-ignored")
    assert Settings.from_env().team_id is None
    assert Settings.from_env().bot_user_id is None
    monkeypatch.delenv("SUMIN_NEXTCLOUD_VERIFY_SSL", raising=False)
    assert Settings.from_env().nextcloud_verify_ssl is True
    monkeypatch.setenv("SUMIN_NEXTCLOUD_VERIFY_SSL", "false")
    assert Settings.from_env().nextcloud_verify_ssl is False
    monkeypatch.setenv("SUMIN_NEXTCLOUD_VERIFY_SSL", " TRUE ")
    assert Settings.from_env().nextcloud_verify_ssl is True
    monkeypatch.setenv("SUMIN_NEXTCLOUD_VERIFY_SSL", "invalid")
    with pytest.raises(ValueError, match="SUMIN_NEXTCLOUD_VERIFY_SSL"):
        Settings.from_env()
    monkeypatch.delenv("SUMIN_NEXTCLOUD_VERIFY_SSL")
    monkeypatch.delenv("AGENT_DATABASE_DSN")
    with pytest.raises(ValueError, match="AGENT_DATABASE_DSN is required"):
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


@pytest.mark.asyncio
async def test_discovers_workspace_and_bot_identity_from_token(settings):
    def handler(request):
        assert request.url.path == "/api/auth.test"
        assert request.method == "POST"
        assert request.headers["authorization"] == "Bearer xoxb-test"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "team_id": TEAM,
                "user_id": "WNEWBOT123",
                "bot_id": "B12345678",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        configured = replace(settings, team_id=None, bot_user_id=None)
        discovered = await configured.discover_identity(
            SlackFiles(settings.bot_token, http)
        )
        assert discovered.team_id == TEAM and discovered.bot_user_id == "WNEWBOT123"
        assert configured.team_id is None
        assert normalize(envelope(user="WNEWBOT123"), discovered) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        {"ok": False, "error": "secret-provider-response"},
        {"ok": True, "user_id": "UBOT", "bot_id": "B123"},
        {"ok": True, "team_id": TEAM, "user_id": "UBOT"},
        {"ok": True, "team_id": TEAM, "user_id": "invalid", "bot_id": "B123"},
    ],
)
async def test_identity_discovery_rejects_invalid_auth_or_non_bot(result, settings):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=result))
    ) as http:
        with pytest.raises(FileIntegrationError) as exc:
            await settings.discover_identity(SlackFiles(settings.bot_token, http))
        assert "secret-provider-response" not in str(exc.value)


@pytest.mark.asyncio
async def test_new_public_and_private_channels_without_config_change(settings):
    agent = service(settings)
    for channel in ("CNEWCHAN1", "GPRIVATE1"):
        work = normalize(envelope(channel=channel), settings)[0]
        assert work.channel_id == channel
        assert await agent.run(work) == "archived"
    assert len(agent.store.folders) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"is_member": False},
        {"is_member": "true"},
        {"id": "COTHER123"},
        {"is_im": True},
        {"is_mpim": True},
    ],
)
async def test_live_membership_gates_all_outbound_replies(overrides):
    from ax_integrations.slack import SlackMessage
    from ax_integrations.slack_files import MemberSlackService

    slack = SimpleNamespace(
        info=AsyncMock(
            return_value={
                "channel": {
                    "id": CHANNEL,
                    "is_member": True,
                    **overrides,
                }
            }
        )
    )
    slack.member_channel = lambda channel: SlackFiles.member_channel(slack, channel)
    client = SimpleNamespace(chat_postMessage=AsyncMock())
    sender = MemberSlackService("xoxb-test", slack, client=client)
    with pytest.raises(FileIntegrationError):
        await sender.send_message(SlackMessage(channel_id=CHANNEL, text="result"))
    client.chat_postMessage.assert_not_called()


@pytest.mark.asyncio
async def test_dynamic_sender_allows_new_channels_but_rechecks_removal():
    from ax_integrations.slack import SlackMessage
    from ax_integrations.slack_files import MemberSlackService

    current = {"id": "CNEWCHAN1", "is_member": True}
    slack = SimpleNamespace(info=AsyncMock(return_value={"channel": current}))
    slack.member_channel = lambda channel: SlackFiles.member_channel(slack, channel)
    client = SimpleNamespace(
        chat_postMessage=AsyncMock(return_value={"ok": True, "ts": "123.456"})
    )
    sender = MemberSlackService("xoxb-test", slack, client=client)
    message = SlackMessage(channel_id="CNEWCHAN1", text="result", thread_ts="123.456")
    assert (await sender.send_message(message)).success
    current["is_member"] = False
    with pytest.raises(FileIntegrationError):
        await sender.send_message(message)
    assert client.chat_postMessage.await_count == 1
    assert slack.info.await_count == 2


@pytest.mark.asyncio
async def test_unresolved_identity_refuses_ingress(settings):
    store = SimpleNamespace(enqueue=AsyncMock())
    app = create_app(replace(settings, team_id=None, bot_user_id=None), store)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        body, headers = signed(envelope())
        assert (
            await client.post("/slack/events", content=body, headers=headers)
        ).status_code == 503
        assert (await client.get("/readyz")).status_code == 503
        store.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_api_startup_discovers_identity_before_accepting_events(
    settings, monkeypatch
):
    from contextlib import asynccontextmanager

    from apps.sumin import main

    monkeypatch.setattr(
        main.Settings,
        "from_env",
        lambda: replace(settings, team_id=None, bot_user_id=None),
    )
    discover = AsyncMock(return_value=settings)
    monkeypatch.setattr(main.Settings, "discover_identity", discover)
    pool = SimpleNamespace(fetchval=AsyncMock(return_value=1))

    @asynccontextmanager
    async def pool_context(*args, **kwargs):
        yield pool

    monkeypatch.setattr(main.asyncpg, "create_pool", pool_context)
    app = main.create_application()
    assert app.state.settings.team_id is None
    async with app.router.lifespan_context(app):
        assert app.state.settings.team_id == TEAM
        assert app.state.settings.bot_user_id == settings.bot_user_id
    discover.assert_awaited_once()


def test_group_dm_events_are_ignored(settings):
    assert normalize(envelope(channel="G12345678", channel_type="mpim"), settings) == []


@pytest.mark.asyncio
async def test_sumin_management_uses_shared_agent_database(monkeypatch):
    from apps.sumin import manage

    monkeypatch.setenv("AGENT_DATABASE_DSN", "postgresql://shared-agent-database")
    monkeypatch.setenv("SUMIN_DATABASE_DSN", "postgresql://obsolete-database")
    connection = SimpleNamespace(fetch=AsyncMock(return_value=[]), close=AsyncMock())
    connect = AsyncMock(return_value=connection)
    monkeypatch.setattr(manage.asyncpg, "connect", connect)
    await manage.execute(SimpleNamespace(command="status"))
    connect.assert_awaited_once_with(
        "postgresql://shared-agent-database", command_timeout=30
    )
    connection.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("verify_ssl", [True, False])
async def test_worker_nextcloud_tls_setting_is_isolated(
    settings, monkeypatch, verify_ssl
):
    from contextlib import asynccontextmanager
    from unittest.mock import Mock

    from apps.workers import sumin as worker

    configured = replace(
        settings, nextcloud_verify_ssl=verify_ssl, nextcloud_ca_bundle="/test/ca.pem"
    )
    monkeypatch.setattr(worker.Settings, "from_env", lambda: configured)
    tls_context = object()
    create_context = Mock(return_value=tls_context)
    monkeypatch.setattr(worker.ssl, "create_default_context", create_context)
    clients = []

    @asynccontextmanager
    async def client_context(**kwargs):
        clients.append(kwargs)
        yield object()

    @asynccontextmanager
    async def pool_context(*args, **kwargs):
        yield object()

    class StartupComplete(Exception):
        pass

    monkeypatch.setattr(worker.httpx, "AsyncClient", client_context)
    monkeypatch.setattr(worker.asyncpg, "create_pool", pool_context)
    monkeypatch.setattr(
        worker.Settings, "discover_identity", AsyncMock(side_effect=StartupComplete)
    )
    with pytest.raises(StartupComplete):
        await worker.run()
    assert clients[0].get("verify", True) is True
    assert clients[1]["verify"] is (tls_context if verify_ssl else False)
    if verify_ssl:
        create_context.assert_called_once_with(cafile="/test/ca.pem")
    else:
        create_context.assert_not_called()

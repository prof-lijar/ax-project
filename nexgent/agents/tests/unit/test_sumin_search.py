"""Model-driven tool contracts: no provider/network calls in unit tests."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from ax_contracts.sumin import SuminTask
from ax_integrations.file_http import FileIntegrationError
from ax_integrations.nextcloud import CloudFile

from workflows.sumin.search import FileSearchAgent
from workflows.sumin.store import Store

FILE = "F0C2B6R164U"
NAME = FILE + "--Nexgent_AX_CEO_Briefing_20260821_Last_Two_Slides_Added (2).pdf"
ROW = {
    "file_id": FILE,
    "archive_name": NAME,
    "filename": NAME.split("--", 1)[1],
    "uploaded_at": "2026-09-16T09:00:00+00:00",
    "first_seen_at": "2026-09-16T09:01:00+00:00",
    "uploader_id": "U12345678",
    "upload_context": "회의 자료 공유합니다",
}
TASK = SuminTask(
    event_id="EvSearch",
    team_id="T12345678",
    channel_id="C12345678",
    kind="search",
    message_ts="1789549500.000001",
    text="<@U12345678> 아까 방금 올렸던 대표님에게 브리핑 자료 알려줘",
)


def action(name, ids=(), terms=(), offset=0, message=""):
    return SimpleNamespace(
        text=json.dumps(
            {
                "action": name,
                "terms": list(terms),
                "offset": offset,
                "file_ids": list(ids),
                "message": message,
            },
            ensure_ascii=False,
        )
    )


def setup(actions, rows=None, live=True):
    store = SimpleNamespace(
        search_metadata=AsyncMock(return_value=[ROW] if rows is None else rows)
    )
    cloud = SimpleNamespace(
        list_files=AsyncMock(
            return_value=[CloudFile(NAME, "https://cloud.example/f/1")] if live else []
        )
    )
    model = SimpleNamespace(complete_structured=AsyncMock(side_effect=actions))
    return FileSearchAgent(store, cloud, model), store, cloud, model


@pytest.mark.asyncio
async def test_korean_request_browses_inspects_verifies_and_selects_english_briefing():
    agent, store, cloud, model = setup(
        [
            action("search_metadata"),
            action("inspect_files", [FILE]),
            action("verify_files", [FILE]),
            action("finish", [FILE], message="방금 올린 대표님 브리핑 자료입니다."),
        ]
    )
    result = await agent.find(TASK, "Shared/Slack/nexgent-test")
    assert result.files[0].name == NAME
    assert result.message.startswith("방금")
    store.search_metadata.assert_awaited_once_with(TASK, [], 0)
    cloud.list_files.assert_awaited_once_with("Shared/Slack/nexgent-test")
    assert model.complete_structured.await_count == 4
    messages = model.complete_structured.call_args.args[0]
    assert any("uploaded_at" in msg["content"] for msg in messages)
    assert any("회의 자료" in msg["content"] for msg in messages)


@pytest.mark.asyncio
async def test_model_can_reformulate_and_paginate_after_empty_search():
    agent, store, _, _ = setup(
        [
            action("search_metadata", terms=["대표님"]),
            action("search_metadata", terms=["CEO", "briefing"], offset=20),
            action("inspect_files", [FILE]),
            action("verify_files", [FILE]),
            action("finish", [FILE]),
        ]
    )
    store.search_metadata.side_effect = [[], [ROW]]
    assert (await agent.find(TASK, "Slack/test")).files
    assert store.search_metadata.await_args_list[1].args == (
        TASK,
        ["CEO", "briefing"],
        20,
    )


@pytest.mark.asyncio
async def test_unknown_or_unverified_ids_cannot_be_sent():
    agent, _, cloud, _ = setup(
        [
            action("finish", ["FUNKNOWN"]),
            action("search_metadata"),
            action("finish", [FILE]),
            action("verify_files", [FILE]),
            action("clarify", message="어떤 자료를 찾으시나요?"),
        ]
    )
    result = await agent.find(TASK, "Slack/test")
    assert not result.files
    cloud.list_files.assert_not_awaited()


@pytest.mark.asyncio
async def test_deleted_candidate_is_not_returned():
    agent, _, _, _ = setup(
        [
            action("search_metadata"),
            action("inspect_files", [FILE]),
            action("verify_files", [FILE]),
            action("finish", [FILE]),
            action("clarify", message="보관 폴더에서 파일을 찾지 못했습니다."),
        ],
        live=False,
    )
    assert not (await agent.find(TASK, "Slack/test")).files


@pytest.mark.asyncio
async def test_ambiguity_requests_clarification_without_uploads():
    agent, _, cloud, _ = setup(
        [
            action("search_metadata"),
            action("clarify", message="8월 자료와 9월 자료 중 어느 것인가요?"),
        ]
    )
    result = await agent.find(TASK, "Slack/test")
    assert not result.files
    assert "어느" in result.message
    cloud.list_files.assert_not_awaited()


@pytest.mark.asyncio
async def test_malformed_or_unbounded_actions_stop_after_eight_turns():
    agent, store, _, model = setup([SimpleNamespace(text="not json")] * 8)
    result = await agent.find(TASK, "Slack/test")
    assert not result.files
    assert model.complete_structured.await_count == 8
    store.search_metadata.assert_not_awaited()


@pytest.mark.asyncio
async def test_injected_channel_or_sql_is_rejected_by_action_schema():
    malicious = action("search_metadata")
    payload = json.loads(malicious.text)
    payload["channel_id"] = "CPRIVATE1"
    payload["sql"] = "SELECT * FROM agent.sumin_files"
    malicious.text = json.dumps(payload)
    agent, store, _, _ = setup(
        [malicious, action("clarify", message="검색 요청을 구체적으로 알려주세요.")]
    )
    assert not (await agent.find(TASK, "Slack/test")).files
    store.search_metadata.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_failure_is_sanitized_not_reported_as_no_match():
    agent, _, _, _ = setup(RuntimeError("secret credential and provider body"))
    with pytest.raises(FileIntegrationError, match="^sumin_search_failed$"):
        await agent.find(TASK, "Slack/test")


@pytest.mark.asyncio
async def test_metadata_query_is_parameterized_and_channel_scoped():
    pool = SimpleNamespace(fetch=AsyncMock(return_value=[]))
    await Store(pool).search_metadata(TASK, ["'; DROP TABLE agent.sumin_files; --"], 20)
    sql, team, channel, terms, offset = pool.fetch.call_args.args
    assert "f.team_id=$1 AND f.channel_id=$2" in sql
    assert team == TASK.team_id and channel == TASK.channel_id
    assert terms == ["'; DROP TABLE agent.sumin_files; --"]
    assert "DROP TABLE" not in sql and offset == 20


@pytest.mark.asyncio
async def test_metadata_records_true_slack_upload_time():
    pool = SimpleNamespace(execute=AsyncMock())
    work = TASK.model_copy(update={"kind": "archive", "file_id": FILE})
    await Store(pool).save_file_metadata(
        work, {"name": "briefing.pdf", "created": 1789549200, "user": "UOWNER123"}
    )
    assert pool.execute.call_args.args[1:] == (
        TASK.team_id,
        TASK.channel_id,
        FILE,
        "briefing.pdf",
        1789549200,
        "UOWNER123",
    )

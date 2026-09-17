"""Opt-in model evaluation with synthetic metadata; never sends Slack messages."""

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from ax_contracts.sumin import SuminTask
from ax_integrations.chat import OpenAICompatibleChatModel, OpenAICompatibleSettings
from ax_integrations.nextcloud import CloudFile

from workflows.sumin.search import FileSearchAgent


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "아까 방금 올렸던 대표님에게 브리핑 자료 알려줘",
        "Please find the CEO briefing I just uploaded, not the older version.",
    ],
)
async def test_live_model_selects_recent_briefing_across_languages(query):
    if os.environ.get("SUMIN_RUN_MODEL_EVAL") != "1":
        pytest.skip("Set SUMIN_RUN_MODEL_EVAL=1 with configured model credentials")
    now = datetime.now(UTC)
    rows = []
    for file_id, name, uploaded in [
        (
            "FNEW12345",
            "Nexgent_AX_CEO_Briefing_20260821.pdf",
            now - timedelta(minutes=2),
        ),
        ("FOLD12345", "Nexgent_AX_CEO_Briefing_20260901.pdf", now - timedelta(days=7)),
        ("FOTHER123", "Nexgent_developer_notes.md", now - timedelta(minutes=1)),
    ]:
        rows.append(
            {
                "file_id": file_id,
                "archive_name": file_id + "--" + name,
                "filename": name,
                "uploaded_at": uploaded.isoformat(),
                "first_seen_at": uploaded.isoformat(),
                "uploader_id": "U12345678",
                "upload_context": "Uploaded document",
            }
        )
    store = SimpleNamespace(search_metadata=AsyncMock(return_value=rows))
    cloud = SimpleNamespace(
        list_files=AsyncMock(
            return_value=[
                CloudFile(
                    row["archive_name"], "https://example.invalid/f/" + row["file_id"]
                )
                for row in rows
            ]
        )
    )
    model = OpenAICompatibleChatModel(OpenAICompatibleSettings.from_env())
    try:
        task = SuminTask(
            event_id="EvEval",
            team_id="T12345678",
            channel_id="C12345678",
            kind="search",
            message_ts=str(now.timestamp()),
            text=query,
        )
        result = await FileSearchAgent(store, cloud, model).find(task, "Slack/test")
        assert [file.name for file in result.files] == [rows[0]["archive_name"]]
        assert cloud.list_files.await_count >= 1
    finally:
        await model.aclose()

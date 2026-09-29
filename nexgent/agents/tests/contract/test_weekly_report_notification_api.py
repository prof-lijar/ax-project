"""Validate the producer body against the actual product backend contract."""

import importlib.util
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from tests.unit.test_weekly_report_completion_notification import snapshot
from workflows.weekly_report.completion_notification import notification_payload
from workflows.weekly_report.failure_notification import failure_payload


def test_completion_payload_matches_backend_notification_contract():
    schema = (
        Path(__file__).resolve().parents[3] / "backend/app/notifications/schemas.py"
    )
    if not schema.exists():
        pytest.skip("product backend checkout is required")
    spec = importlib.util.spec_from_file_location("backend_notification_schema", schema)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = notification_payload(
        snapshot(), week_start="2026-09-21", destination="default"
    )
    parsed = module.SlackNotification.model_validate(payload)
    assert parsed.text == payload["text"]
    assert parsed.destination == "default"
    assert len(parsed.blocks) == 7
    TypeAdapter(module.RequestKey).validate_python(
        "weekly-report:production:2026-09-21:coverage-v1"
    )

    # Exercise the actual backend renderer: Markdown-looking text would not
    # become a table because this service intentionally uses plain_text blocks.
    renderer_spec = importlib.util.spec_from_file_location(
        "backend_notification_renderer", schema.with_name("slack.py")
    )
    renderer = importlib.util.module_from_spec(renderer_spec)
    renderer_spec.loader.exec_module(renderer)
    message = renderer.render_message(
        {
            "id": "8ff04888-a682-4704-8d27-3d5cd2cb26cb",
            "channel_id": "C0123456789",
            "payload": parsed.model_dump(mode="json"),
        }
    )
    assert message["blocks"][0]["text"]["text"] == "주간 리포트 저장 현황"
    tables = [block for block in message["blocks"] if block["type"] == "table"]
    assert len(tables) == 1 and len(tables[0]["rows"]) == 11
    assert all(len(row) == 7 for row in tables[0]["rows"])
    assert all(cell["type"] == "raw_text" for row in tables[0]["rows"] for cell in row)
    assert "WARNING" not in message["text"]
    for row in payload["blocks"][4]["rows"]:
        assert " | ".join(cell["text"] for cell in row) in message["text"]
    assert (
        message["blocks"][-1]["text"]["text"] == payload["blocks"][-1]["text"]["text"]
    )
    assert len(parsed.text) < 3000


@pytest.mark.parametrize("reason", ["error", "terminated", "heartbeat", "overdue", "missed"])
def test_failure_payload_matches_backend_native_blocks(reason):
    schema = Path(__file__).resolve().parents[3] / "backend/app/notifications/schemas.py"
    if not schema.exists():
        pytest.skip("product backend checkout is required")
    spec = importlib.util.spec_from_file_location("backend_failure_schema", schema)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = failure_payload(
        {"week_start": "2026-09-21", "stage": "generation", "reason": reason,
         "run_id": "8ff04888-a682-4704-8d27-3d5cd2cb26cb",
         "job": {"status": "failed", "discovered_count": 6601,
                 "completed_count": 6600, "failed_count": 1}},
        observed_at="2026-09-28T02:00:00+09:00", destination="default",
    )
    parsed = module.SlackNotification.model_validate(payload)
    assert parsed.locale == "ko"
    assert parsed.severity == "error"
    assert len(parsed.blocks) == 4
    assert parsed.blocks[2].type == "table"
    for row in payload["blocks"][2]["rows"][1:]:
        assert f"{row[0]['text']}: {row[1]['text']}" in parsed.text
    TypeAdapter(module.RequestKey).validate_python(
        "weekly-report:failure:8ff04888-a682-4704-8d27-3d5cd2cb26cb"
    )

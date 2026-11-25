"""Kakao worksheet commands through the desktop request and receipt boundary."""

import json
import threading
from itertools import permutations
from dataclasses import asdict
from unittest.mock import Mock

import pytest

from app.api.incoming_llm import parse_incoming
from app.api.operations_client import OperationsResult, OperationsSettings
from app.api.unified_operations import UnifiedOperationsClient
from app.api.workflow_requests import kakao_command
from app.automation.installation_sms import InstallationSMS
from app.automation.unified_workflow import UnifiedProcessor
from app.models import AgentError
from app.storage.image_reply_queue import ImageReplyQueue
from app.storage.operation_journal import OperationJournal

GUARDIAN = "보호자 추가/가상길 1/가상인/가상림/010-0000-0001/딸"
DATE = "2026-11-20"


@pytest.mark.parametrize(
    ("message", "workflow"),
    [
        ("정보수정/가상인/가상길 1/01000000001", "information_update"),
        ("정보수정/생년월일/가상인/가상길 1/83.01.09", "information_update"),
        ("정보수정/이름/가상인/가상길 1/가상림", "information_update"),
        ("정보수정/성별/가상인/가상길 1/여성", "information_update"),
        ("정보수정/주소/가상인/새길 2", "information_update"),
        (GUARDIAN, "information_update"),
        (GUARDIAN.replace("추가", "수정"), "information_update"),
        ("기기교체/가상인/가상길 1/00001234", "device_replacement"),
        ("기기회수/가상인/가상길 1", "device_collection"),
        ("기기분실/가상인/가상길 1", "device_loss"),
        ("설치확인/가상인/가상길 1", "installation_confirmation"),
        ("고장확인/00001234", "fault_confirmation"),
    ],
)
def test_worksheet_payloads(message, workflow):
    client = UnifiedOperationsClient(OperationsSettings("https://example.test", "admin"), "test")
    expected = {"source": "kakao", "workflow_id": workflow, "message": message}
    if workflow in {"device_replacement", "device_collection", "fault_confirmation"}:
        expected["manager"] = "관리인"
    if workflow in {"fault_confirmation", "device_loss"}:
        expected["received_date"] = DATE
    assert client.request_payload(kakao_command(message, "관리인", DATE)) == expected
    with pytest.raises(AgentError):
        client.request_payload({**expected, "confirmed_fault": True})


def test_capture_attributes_bubble_senders_and_freezes_request_for_replay(queue):
    jobs = ImageReplyQueue(queue)
    journal = OperationJournal(queue)
    job, _ = jobs.enqueue_pair("chat", b"a", b"b")
    first, second = "기기교체/가상인/가상길 1/00001234", "고장확인/00001234"
    incoming = parse_incoming(
        json.dumps(
            {
                "kind": "incoming",
                "sender": "",
                "is_ai": False,
                "text": [{"text": first, "sender": "관리인"}, {"text": second, "sender": "다른이"}],
            }
        ),
        batch=True,
    )
    api = Mock()
    api.run.return_value = OperationsResult("blocked", "확인해 주세요.")
    processor = UnifiedProcessor(journal, api)
    for capture_date in (DATE, "2026-11-25"):
        assert processor.answer(None, incoming, job, threading.Event(), received_date=capture_date)
    assert [call.args[0] for call in api.run.call_args_list] == [
        kakao_command(first, "관리인"),
        kakao_command(second, "다른이", DATE),
    ]
    assert kakao_command(second) == {
        "source": "kakao",
        "workflow_id": "fault_confirmation",
        "message": second,
    }

    new_job, _ = jobs.enqueue_pair("chat", b"c", b"d")
    assert journal.previously_attempted("chat", kakao_command(second, "다른이", DATE), new_job)
    assert not journal.previously_attempted(
        "chat", kakao_command(second, "다른이", "2026-11-25"), new_job
    )


def guardian_response():
    return {
        "api_version": "1",
        "workflow_id": "information_update",
        "status": "completed",
        "verified": True,
        "response": "가입자 명부와 보호자 연결을 확인했습니다.",
        "receipts": {
            key: {"status": "updated", "verified": True, "rows": [3]}
            for key in ("roster", "as_update", "member_note")
        },
        "sms": {
            "should_send": True,
            "recipients": ["01000000001"],
            "title": "안내",
            "text": "앱 안내",
        },
    }


@pytest.mark.parametrize("invalid", ["recipient", "correction", "receipt"])
def test_guardian_guide_requires_exact_new_recipient_and_verified_stages(invalid):
    client = UnifiedOperationsClient(OperationsSettings("https://example.test", "admin"), "test")
    response = guardian_response()
    message = GUARDIAN
    if invalid == "recipient":
        response["sms"]["recipients"] = ["01000000002"]
    elif invalid == "correction":
        message = message.replace("추가", "수정")
    else:
        response["receipts"]["member_note"]["verified"] = False
    with pytest.raises(AgentError):
        client.parse_run_result(response, kakao_command(message))


def test_guardian_guide_is_sent_once_on_replay(config, queue, monkeypatch):
    jobs = ImageReplyQueue(queue)
    journal = OperationJournal(queue)
    job, _ = jobs.enqueue_pair("chat", b"a", b"b")
    client = UnifiedOperationsClient(OperationsSettings("https://example.test", "admin"), "test")
    result = asdict(client.parse_run_result(guardian_response(), kakao_command(GUARDIAN)))
    bizgo = Mock()
    bizgo.prepare_installation.return_value = ["guide"]
    config.bizgo_installation_test = config.bizgo_sandbox = False
    monkeypatch.setattr("app.automation.installation_sms.create_bizgo", lambda *a, **kw: bizgo)
    sms = InstallationSMS(config, journal, queue.event, lambda _: None)
    sms.record_routing(job)
    for _ in range(2):
        reply = sms.reply(result, job, job + "-0:sms", threading.Event())
        assert "0001" in reply and reply.startswith(result["response"])
    bizgo.send.assert_called_once()

@pytest.mark.parametrize("fields", permutations(("기기교체", "가상인", "가상로 8길 58", "0217")))
def test_replacement_capture_preserves_each_field_order(fields):
    message = "/".join(fields)
    request = kakao_command(message, "관리인")
    client = UnifiedOperationsClient(OperationsSettings("https://example.test", "admin"), "test")
    assert client.request_payload(request) == {
        "source": "kakao", "workflow_id": "device_replacement", "message": message, "manager": "관리인",
    }

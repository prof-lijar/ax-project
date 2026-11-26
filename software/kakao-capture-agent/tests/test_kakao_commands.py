"""Kakao worksheet commands through the desktop request and receipt boundary."""

import json
import threading
from itertools import permutations
from dataclasses import asdict
from unittest.mock import Mock

import pytest

from app.api.incoming_llm import IncomingAnalysisError, IncomingMessage, parse_incoming
from app.api.operations_client import OperationsResult, OperationsSettings
from app.api.unified_operations import UnifiedOperationsClient
from app.api.workflow_requests import extract_sources, kakao_command
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


@pytest.mark.parametrize(
    "second_label",
    [{}, {"sender": None}, {"sender": ["관리인"]}, {"sender": "관리\n인"}, {"sender": "가" * 101}],
)
def test_identical_power_requests_with_unavailable_sender_run_once_per_bubble(queue, second_label):
    message = "가상인 / 경기 광명시 가상로 238 / 전원연결"
    body = {
        "kind": "incoming",
        "sender": "관리인",
        "is_ai": False,
        "text": [{"text": message, "sender": "관리인"}, {"text": message, **second_label}],
    }
    incoming = parse_incoming(json.dumps(body), batch=True)
    assert incoming.bubble_senders == ("관리인", "")
    jobs = ImageReplyQueue(queue)
    job, _ = jobs.enqueue_pair("chat", b"before", b"after")
    operations = Mock()
    operations.run.side_effect = [OperationsResult("completed", reply) for reply in ("첫째", "둘째")]
    processor = UnifiedProcessor(OperationJournal(queue), operations)
    for _ in range(2):
        assert processor.answer(None, incoming, job, threading.Event()) == "첫째\n\n둘째"
    requests = [call.args[0] for call in operations.run.call_args_list]
    assert [(request["action"], request["message"]) for request in requests] == [
        ("전원연결", message), ("전원연결", message),
    ]


def test_legacy_transcript_of_complete_power_commands_keeps_both_occurrences():
    message = "가상인 / 경기 광명시 가상로 238 / 전원연결"
    incoming = IncomingMessage("incoming", f"{message}\n\n{message}")
    assert extract_sources(None, incoming, threading.Event()) == [message, message]


def test_failed_request_in_burst_leaves_following_requests_ready_after_recovery(queue, monkeypatch):
    jobs = ImageReplyQueue(queue)
    journal = OperationJournal(queue)
    original, _ = jobs.enqueue_pair("chat", b"before", b"burst")
    journal.claim(original + ":sms-routing", original, "captured-routing")
    later, _ = jobs.enqueue_pair("chat", b"burst", b"next")
    first = jobs.claim("chat")
    manager_command = "기기회수/가상인/가상로 1"
    incoming = parse_incoming(json.dumps({
        "kind": "incoming", "sender": "", "is_ai": False,
        "text": [{"text": "전원연결??"}, {"text": manager_command, "sender": "관리인"}],
    }), batch=True)
    analyze = Mock(side_effect=IncomingAnalysisError("ambiguous analysis"))
    monkeypatch.setattr("app.automation.unified_workflow.analyze_request", analyze)
    api = Mock()
    processor = UnifiedProcessor(journal, api)
    with pytest.raises(IncomingAnalysisError):
        processor.answer(None, incoming, first["job_id"], threading.Event(), queue_each_request=True)
    api.run.assert_not_called()
    jobs.finish(original, "review")
    jobs = ImageReplyQueue(queue)
    sibling = jobs.claim("chat")
    key = sibling["job_id"]
    assert sibling["created_at"] == first["created_at"]
    assert journal.get(key + ":sms-routing") == "captured-routing"
    request = kakao_command(manager_command, "관리인")
    assert journal.get(key + ":plan") == [request]
    api.run.return_value = OperationsResult("completed", "확인")
    cancel = threading.Event()
    assert processor.answer(None, IncomingMessage("incoming", manager_command), key, cancel) == "확인"
    api.run.assert_called_once_with(request, cancel)
    jobs.finish(key, "sent")
    assert jobs.claim("chat")["job_id"] == later


@pytest.mark.parametrize("command,args", [
    ("기기회수", ["가상인", "가상로 1"]),
    ("정보수정", ["성별", "가상인", "가상로 1", "여성"]),
    ("보호자 추가", GUARDIAN.split("/")[1:]),
    ("고장확인", ["00001234"]),
])
def test_worksheet_keyword_in_each_slot_reaches_expected_endpoint_payload(command, args):
    client = UnifiedOperationsClient(OperationsSettings("https://example.test", "admin"), "test")
    expected = kakao_command("/".join([command, *args]), "관리인", DATE)
    for index in range(len(args) + 1):
        message = " / ".join([*args[:index], command, *args[index:]])
        request = kakao_command(message, "관리인", DATE)
        payload = client.request_payload(request)
        assert payload == {**expected, "message": message if index == 0 else expected["message"]}


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

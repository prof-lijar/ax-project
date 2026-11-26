"""The desktop device command uses the same payload and reply as the web workbench."""

import json
import threading
from itertools import permutations

import httpx
import pytest

from app.api.incoming_llm import IncomingMessage
from app.api.operations_client import OperationsSettings
from app.api.unified_operations import UnifiedOperationsClient, parse_unified_result
from app.automation.device_workflow import DeviceProcessor
from app.automation.unified_workflow import UnifiedProcessor
from app.storage.image_reply_queue import ImageReplyQueue
from app.storage.operation_journal import OperationJournal

MESSAGE = "이은경/헌릉로8길58/전원연결"
REPLY = ("[자동 확인]\n이은경님 기기신호 확인 완료입니다.\n\n■ 반영 영역\n"
         "AS 시트 기재 : 패스\n마스터페이지 일반사항 기재 : 완료\n\n감사합니다.")
RESPONSE = {
    "workflow_id": "device_adjustment_power",
    "id": "eff05786-065c-4930-9a9b-97069dc9a35e",
    "started_at": "2026-11-26T09:03:20.839543+00:00", "duration_ms": 17917,
    "status": "completed", "ok": True, "verified": True, "api_version": "1",
    "response": REPLY, "kakao-reply": REPLY,
    "parsed": {"name": "이은경", "lookup_name": "이은경", "address": "헌릉로 8길 58", "mode": "name_address"},
    "roster": {"status": "found", "name": "이은경", "row": 4015},
    "as_lookup": {"status": "not_found", "row": None},
    "as_update": {"status": "skipped", "verified": False, "row": None},
    "signal": {"status": "connected", "connected": True, "fresh": True},
    "member_note": {"status": "already_present", "verified": True},
    "issues": [], "sms": {"should_send": False, "recipients": [], "title": "", "text": ""},
}


@pytest.mark.parametrize("processor_class", [UnifiedProcessor, DeviceProcessor])
@pytest.mark.parametrize("message", ["/".join(fields) for fields in permutations(MESSAGE.split("/"))])
@pytest.mark.parametrize("minimal_response", [False, True])
def test_web_payload_and_exact_response_without_second_llm_or_receipt_checks(
    queue, processor_class, message, minimal_response
):
    jobs = ImageReplyQueue(queue)
    journal = OperationJournal(queue)
    job = jobs.enqueue("chat", "matched incoming action")
    body = ({"workflow_id": "device_adjustment_power", "ok": True, "response": REPLY}
            if minimal_response else RESPONSE)
    posted, debug = [], []

    def server(request):
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={})
        if request.url.path == "/api/me":
            return httpx.Response(200, json={"is_admin": True, "csrf_token": "test"})
        assert str(request.url) == "http://192.168.0.18:5173/api/ax768/runs"
        payload = json.loads(request.content)
        assert payload == {"workflow_id": "device_adjustment_power", "message": message,
                           "confirmed_name": None}
        posted.append(payload)
        return httpx.Response(200, json=body)

    operations = UnifiedOperationsClient(
        OperationsSettings("http://192.168.0.18:5173", "test"), "test-password",
        httpx.MockTransport(server), response_observer=debug.append,
    )
    processor = processor_class(journal, operations)
    incoming = IncomingMessage("incoming", message, bubbles=(message,))
    # No LLM methods exist: any second parse/analysis would fail this test.
    assert processor.answer(object(), incoming, job, threading.Event()) == REPLY
    assert len(posted) == 1 and debug[0]["body"] == body
    audit = journal.get(job + "-0:api")
    assert audit["request"] == posted[0]
    assert audit["original_request"] == message
    assert audit["api_response"] == body and audit["outgoing_text"] == REPLY
    assert processor.answer(object(), incoming, job, threading.Event()) is None
    assert len(posted) == 1


@pytest.mark.parametrize("metadata", [
    {"kakao-reply": "Different optional text"},
    {"signal": {}, "as_update": {}, "member_note": {}},
    {"verified": False, "issues": None, "id": None, "sms": None},
])
def test_ok_true_is_the_device_success_decision_and_response_is_the_reply(metadata):
    body = {**RESPONSE, **metadata}
    result = parse_unified_result(body)
    assert result.completed and result.response == REPLY
    assert result.api_response == body

import json
import threading
from itertools import permutations
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from app.api.incoming_llm import IncomingAnalysisError, IncomingMessage
from app.api.operations_client import OperationsResult, OperationsSettings, credential_destination
from app.api.unified_operations import UnifiedOperationsClient, parse_unified_result
from app.api.workflow_requests import parse_sources
from app.automation.unified_workflow import UnifiedProcessor, UnifiedWorkflow
from app.models import AgentError, Cancelled
from app.storage.image_reply_queue import ImageReplyQueue
from app.storage.operation_journal import OperationJournal
from tests.test_device_workflow import forbid_device_sms, receipt  # noqa: F401
from tests.test_queued_visual_catch import watching  # noqa: F401

MESSAGE = "위치조정/이영희/광명시 OO동 OO로 56"
REPLY = "[자동 확인]\n이영희님 기기 위치변경 후 기기신호 확인 완료입니다.\n내용 기재해두었습니다.\n감사합니다. :)"
POWER_MESSAGE = "전원연결/박철수/울진군 OO면 OO길 78 "
POWER_REPLY = "[자동 확인]\n박철수님 기기 전원연결 후 기기신호 확인 완료입니다.\n내용 기재해두었습니다.\n감사합니다. :)"


@pytest.mark.parametrize("message,action,reply", [
    (MESSAGE, "기기위치조정", REPLY),
    (POWER_MESSAGE, "전원연결", POWER_REPLY),
])
def test_unified_transport(message, action, reply):
    calls = []

    def server(request):
        calls.append(request.url.path)
        if request.url.path == "/auth/login":
            return httpx.Response(
                200, json={}, headers={"set-cookie": "session=test; Path=/; HttpOnly"}
            )
        assert request.headers["cookie"] == "session=test"
        if request.url.path == "/api/me":
            return httpx.Response(200, json={"is_admin": True, "csrf_token": "csrf"})
        assert request.url.path == "/api/ax768/runs"
        assert request.headers["x-csrf-token"] == "csrf"
        assert json.loads(request.content) == {
            "workflow_id": "device_adjustment_power",
            "message": message,
            "confirmed_name": None,
            "action": action,
        }
        return httpx.Response(
            200, json={**receipt(), "api_version": "1", "verified": True, "response": reply}
        )

    client = UnifiedOperationsClient(
        OperationsSettings("https://nexgent.test", "admin"), "secret", httpx.MockTransport(server)
    )
    assert client.run(message, threading.Event()).response == reply
    assert calls == ["/auth/login", "/api/me", "/api/ax768/runs"]


@pytest.mark.parametrize("path", ["", "/agents/ax768", "/api/ax768/runs"])
def test_user_url(config, path):
    config.operations_url = "http://192.168.0.18:5173" + path
    config.operations_allow_http = True
    config.operations_username = "admin"
    config.validate()
    assert OperationsSettings.resolve(config).url == "http://192.168.0.18:5173"
    assert (
        credential_destination(config.operations_url, "admin")
        == "operations:http://192.168.0.18:5173:admin"
    )


def test_source_extraction_keeps_all_text():
    sources = [MESSAGE, "정보수정/김영희/전화번호 변경 요청"]
    incoming = IncomingMessage("incoming", "\n".join(sources))
    assert parse_sources(json.dumps({"requests": sources}), incoming) == sources
    for invalid in [sources[::-1], [MESSAGE], ["없는 요청"]]:
        with pytest.raises(IncomingAnalysisError):
            parse_sources(json.dumps({"requests": invalid}), incoming)
    with pytest.raises(IncomingAnalysisError):
        parse_sources(
            json.dumps({"requests": [MESSAGE]}),
            IncomingMessage("incoming", "예시: " + MESSAGE + " 취소합니다"),
        )


@pytest.mark.parametrize("status", ["completed", "disconnected", "needs_confirmation"])
def test_exact_reply_once(queue, monkeypatch, status):
    operations = SimpleNamespace(
        run=Mock(return_value=OperationsResult(status, REPLY, status == "completed"))
    )
    ImageReplyQueue(queue)
    processor = UnifiedProcessor(OperationJournal(queue), operations)
    monkeypatch.setattr("app.automation.unified_workflow.extract_sources", lambda *a: [MESSAGE])
    for _ in range(2):
        assert (
            processor.answer(None, IncomingMessage("incoming", MESSAGE), "job", threading.Event())
            == REPLY
        )
    operations.run.assert_called_once()
    assert operations.run.call_args.args[0] == MESSAGE
    assert UnifiedWorkflow.format_reply(None, REPLY) == REPLY


@pytest.mark.parametrize("kind,text", [
    ("incoming", "안녕하세요"),
    ("incoming", "이영희/광명시 OO동 OO로 56"),
    ("incoming", "정보수정/이영희/전화번호 변경"),
    ("incoming", "위치변경/이영희/광명시 OO동 OO로 56"),
    ("incoming", "[자동 확인]\n위치조정 완료"),
    ("outgoing", MESSAGE),
    ("outgoing", POWER_MESSAGE),
    ("incoming", "[자동 확인]\n전원연결 완료"),
    ("none", MESSAGE),
    ("uncertain", MESSAGE),
])
def test_unmatched_or_nonincoming_never_extracts_or_calls_api(queue, monkeypatch, kind, text):
    ImageReplyQueue(queue)
    operations = SimpleNamespace(run=Mock())
    extract = Mock(side_effect=AssertionError("Ignored messages must not be split"))
    monkeypatch.setattr("app.automation.unified_workflow.extract_sources", extract)
    processor = UnifiedProcessor(OperationJournal(queue), operations)
    assert processor.answer(None, IncomingMessage(kind, text), "ignored", threading.Event()) is None
    extract.assert_not_called()
    operations.run.assert_not_called()


@pytest.mark.parametrize("fields", [
    fields for action in ("위치조정", "전원연결")
    for fields in permutations([action, "이영희", "광명시 OO동 OO로 56"])
])
def test_keyword_in_any_field_order(queue, monkeypatch, fields):
    ImageReplyQueue(queue)
    message = "/".join(fields)
    operations = SimpleNamespace(run=Mock(return_value=OperationsResult("completed", REPLY, True)))
    monkeypatch.setattr("app.automation.unified_workflow.extract_sources", lambda *a: [message])
    processor = UnifiedProcessor(OperationJournal(queue), operations)
    assert processor.answer(None, IncomingMessage("incoming", message), "job", threading.Event()) == REPLY
    assert operations.run.call_args.args[0] == message


@pytest.mark.parametrize("resume", [False, True])
def test_mixed_batch_filters_each_message_and_saved_replies(queue, monkeypatch, resume):
    ImageReplyQueue(queue)
    journal = OperationJournal(queue)
    plan = ["안녕하세요", MESSAGE, "정보수정/김영희/전화번호 변경 요청"]
    operations = SimpleNamespace(run=Mock(return_value=OperationsResult("completed", REPLY, True)))
    extract = Mock(return_value=plan)
    monkeypatch.setattr("app.automation.unified_workflow.extract_sources", extract)
    processor = UnifiedProcessor(journal, operations)
    if resume:
        journal.claim("job:plan", "job", plan)
        journal.claim("job:reply", "job", "Old unrelated reply must never be sent")
        journal.claim("job-1:api", "job", {"response": REPLY})
        incoming = UnifiedWorkflow.analyze_job(
            None, None, {"processor": processor, "job_id": "job"}, threading.Event()
        )
    else:
        incoming = IncomingMessage("incoming", "\n".join(plan))
    assert processor.answer(None, incoming, "job", threading.Event()) == REPLY
    if resume:
        extract.assert_not_called()
        operations.run.assert_not_called()
    else:
        operations.run.assert_called_once()
        assert operations.run.call_args.args[0] == MESSAGE
    assert journal.get("job-0:api") is None
    assert journal.get("job-2:api") is None


def test_resumed_unmatched_plan_ignores_old_reply(queue):
    ImageReplyQueue(queue)
    journal = OperationJournal(queue)
    journal.claim("job:plan", "job", ["정보수정/이영희/전화번호 변경 요청"])
    journal.claim("job:reply", "job", "Old unrelated reply must never be sent")
    operations = SimpleNamespace(run=Mock())
    processor = UnifiedProcessor(journal, operations)
    incoming = UnifiedWorkflow.analyze_job(
        None, None, {"processor": processor, "job_id": "job"}, threading.Event()
    )
    assert processor.answer(None, incoming, "job", threading.Event()) is None
    operations.run.assert_not_called()


def test_mixed_location_power_and_chatter_preserves_action_and_reply_order(queue, monkeypatch):
    ImageReplyQueue(queue)
    journal = OperationJournal(queue)
    sources = ["안녕하세요", MESSAGE, POWER_MESSAGE, "감사합니다"]
    monkeypatch.setattr("app.automation.unified_workflow.extract_sources", lambda *a: sources)
    operations = SimpleNamespace(run=Mock(side_effect=[
        OperationsResult("completed", REPLY, True),
        OperationsResult("completed", POWER_REPLY, True),
    ]))
    processor = UnifiedProcessor(journal, operations)
    for _ in range(2):
        assert processor.answer(
            None, IncomingMessage("incoming", "\n".join(sources)), "job", threading.Event()
        ) == REPLY + "\n\n" + POWER_REPLY
    assert [call.args[0] for call in operations.run.call_args_list] == [MESSAGE, POWER_MESSAGE]


def test_two_actions_in_one_message_never_guesses(queue, monkeypatch):
    ImageReplyQueue(queue)
    message = "위치조정 및 전원연결/박철수/울진군 OO면 OO길 78"
    monkeypatch.setattr("app.automation.unified_workflow.extract_sources", lambda *a: [message])
    operations = SimpleNamespace(run=Mock())
    processor = UnifiedProcessor(OperationJournal(queue), operations)
    assert processor.answer(None, IncomingMessage("incoming", message), "job", threading.Event()) is None
    operations.run.assert_not_called()


@pytest.mark.parametrize("message", ["안녕하세요", "위치조정 및 전원연결/박철수/OO길78"])
def test_transport_rejects_missing_or_ambiguous_action_before_network(message):
    calls = []
    client = UnifiedOperationsClient(
        OperationsSettings("https://nexgent.test", "admin"), "secret",
        httpx.MockTransport(lambda request: calls.append(request)),
    )
    with pytest.raises(AgentError, match="single enabled action"):
        client.run(message, threading.Event())
    assert not calls


@pytest.mark.parametrize("error", [AgentError("timeout"), Cancelled("stopped")])
def test_uncertain_operation_never_repeated(queue, monkeypatch, error):
    operations = SimpleNamespace(run=Mock(side_effect=error))
    ImageReplyQueue(queue)
    processor = UnifiedProcessor(OperationJournal(queue), operations)
    monkeypatch.setattr("app.automation.unified_workflow.extract_sources", lambda *a: [MESSAGE])
    if isinstance(error, Cancelled):
        with pytest.raises(Cancelled):
            processor.answer(None, IncomingMessage("incoming", MESSAGE), "job", threading.Event())
    for _ in range(2):
        assert "중복 처리를 막기 위해" in processor.answer(
            None, IncomingMessage("incoming", MESSAGE), "job", threading.Event()
        )
    operations.run.assert_called_once()


def test_response_validation():
    reply = "[자동 확인]\n신호 미확인. "
    body = {
        **receipt(),
        "api_version": "1",
        "verified": False,
        "status": "disconnected",
        "response": reply,
    }
    assert parse_unified_result(body).response == reply
    for invalid in [
        {**body, "response": "x" * 2001},
        {"workflow_id": "information_update", "status": "completed", "response": "done"},
    ]:
        with pytest.raises(AgentError):
            parse_unified_result(invalid)


def test_default_worker(config, queue, region):
    import numpy as np

    from app.automation.monitoring_service import MonitoringService
    from tests.test_automation import Capture, Desktop

    desktop = Desktop(region)
    service = MonitoringService(
        desktop,
        Capture(desktop, np.zeros((100, 80, 3), dtype=np.uint8)),
        queue,
        config,
        lambda *a: None,
        lambda *a: None,
        lambda *a: None,
    )
    assert isinstance(service.auto_catch, UnifiedWorkflow)
    assert service.general_auto_catch is service.auto_catch


@pytest.mark.parametrize("kind,text,should_act", [
    ("incoming", MESSAGE, True),
    ("incoming", "기기" + MESSAGE, True),
    ("incoming", POWER_MESSAGE, True),
    ("incoming", "안녕하세요", False),
    ("incoming", "정보수정/이영희/전화번호 변경", False),
    ("outgoing", MESSAGE, False),
    ("outgoing", POWER_MESSAGE, False),
    ("incoming", "[자동 확인]\n" + MESSAGE, False),
])
def test_screenshot_to_api_reply_keeps_watching(watching, kind, text, should_act):  # noqa: F811
    from tests.test_queued_visual_catch import changed, finish

    w = watching
    w.service.command("stop")
    w.service.dispatch(w.service.commands.get_nowait())
    unified = UnifiedWorkflow(
        w.desktop,
        w.capture,
        w.queue,
        w.service.config,
        w.sender,
        w.service.stop_input,
        lambda png: None,
        lambda message: w.service.transition(w.service.state, message),
    )
    unified.clock = lambda: w.now[0]
    reply = POWER_REPLY if "전원연결" in text else REPLY
    operations = SimpleNamespace(run=Mock(return_value=OperationsResult("completed", reply, True)))
    unified.processor_factory = lambda: UnifiedProcessor(unified.journal, operations)
    w.llm.classify = lambda *a, **kw: IncomingMessage(kind, text)

    async def request(messages, **kwargs):
        assert should_act
        assert json.loads(messages[1]["content"])["text"] == text
        return json.dumps({"requests": [text]})

    async def run_operation(operation, cancel):
        return await operation()

    w.llm.request = request
    w.llm.run_operation = run_operation
    unified.llm_factory = lambda _: w.llm
    unified.sender = SimpleNamespace(
        send=Mock(side_effect=w.sender.send),
        composer_cleared=True,
    )
    w.service.auto_catch = w.service.general_auto_catch = unified
    w.workflow = unified
    w.service.dispatch("auto_catch")
    unified.sender.send.assert_not_called()
    operations.run.assert_not_called()
    assert unified.active
    w.service.command("stop")
    w.service.dispatch(w.service.commands.get_nowait())
    w.service.dispatch("auto_catch")
    unified.sender.send.assert_not_called()
    operations.run.assert_not_called()
    changed(w, 30)
    finish(w)
    assert unified.active
    assert unified.jobs.count(unified.chat_key) == 0
    if should_act:
        assert w.sent == [reply]
        unified.sender.send.assert_called_once_with(reply, require_empty=False)
        operations.run.assert_called_once()
        assert operations.run.call_args.args[0] == text
    else:
        assert w.sent == []
        unified.sender.send.assert_not_called()
        operations.run.assert_not_called()


def test_future_workflow_uses_common_verified_envelope():
    body = {
        "api_version": "1",
        "workflow_id": "future_workflow",
        "status": "completed",
        "verified": True,
        "response": "[자동 확인]\n서버에서 검증한 결과",
    }
    result = parse_unified_result(body)
    assert result.completed and result.response == body["response"]
    for change in [{"api_version": "2"}, {"verified": False}, {"workflow_id": "../other"}]:
        with pytest.raises(AgentError):
            parse_unified_result({**body, **change})

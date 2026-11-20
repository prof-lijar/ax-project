import json
import threading
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
from tests.test_device_workflow import receipt
from tests.test_queued_visual_catch import watching  # noqa: F401

MESSAGE = "위치조정/이영희/광명시 OO동 OO로 56"
REPLY = "[자동 확인]\n이영희님 기기 위치변경 후 기기신호 확인 완료입니다.\n내용 기재해두었습니다.\n감사합니다. :)"


def test_unified_transport():
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
            "workflow_id": "auto",
            "message": MESSAGE,
            "confirmed_name": None,
        }
        return httpx.Response(
            200, json={**receipt(), "api_version": "1", "verified": True, "response": REPLY}
        )

    client = UnifiedOperationsClient(
        OperationsSettings("https://nexgent.test", "admin"), "secret", httpx.MockTransport(server)
    )
    assert client.run(MESSAGE, threading.Event()).response == REPLY
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


def test_screenshot_to_api_reply_keeps_watching(watching):  # noqa: F811
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
    operations = SimpleNamespace(run=Mock(return_value=OperationsResult("completed", REPLY, True)))
    unified.processor_factory = lambda: UnifiedProcessor(unified.journal, operations)
    w.llm.classify = lambda *a, **kw: IncomingMessage("incoming", MESSAGE)

    async def request(messages, **kwargs):
        assert json.loads(messages[1]["content"])["text"] == MESSAGE
        return json.dumps({"requests": [MESSAGE]})

    async def run_operation(operation, cancel):
        return await operation()

    w.llm.request = request
    w.llm.run_operation = run_operation
    unified.llm_factory = lambda _: w.llm
    original_send = w.sender.send
    unified.sender = SimpleNamespace(
        send=lambda text, **kw: (
            "composer cleared" if text == unified.greeting else original_send(text, **kw)
        ),
        composer_cleared=True,
    )
    w.service.auto_catch = w.service.general_auto_catch = unified
    w.workflow = unified
    w.service.dispatch("auto_catch")
    changed(w, 30)
    finish(w)
    assert w.sent == [REPLY]
    assert unified.active
    assert unified.jobs.count(unified.chat_key) == 0
    operations.run.assert_called_once()
    assert operations.run.call_args.args[0] == MESSAGE


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

import json
import threading
from itertools import permutations
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from app.api.incoming_llm import IncomingAnalysisError, IncomingMessage
from app.api.operations_client import OperationsResult, OperationsSettings, credential_destination
from app.api.unified_operations import (
    UnifiedOperationsClient,
    parse_unified_result,
)
from app.api.workflow_requests import (
    analyze_request,
    explicit_device_request,
    parse_analysis,
    parse_sources,
)
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
NATURAL_MESSAGE = "헌릉로8길58 넥스터_이은경님 기기를 다른 곳으로 옮겼습니다"


def model_request(message):
    # Canned model decisions for processor/queue tests; no live model is invoked.
    if message.strip() == "위치조정/이은경/헌릉로8길58":
        return {"message": message, "action": "기기위치조정", "action_text": "위치조정",
                "name": "이은경", "address": "헌릉로8길58"}
    if message == NATURAL_MESSAGE:
        return {"message": message, "action": "기기위치조정",
                "action_text": "기기를 다른 곳으로 옮겼습니다", "name": "넥스터_이은경",
                "address": "헌릉로8길58"}
    if ("위치조정" in message) == ("전원연결" in message):
        return None
    if "전원연결" in message:
        return {"message": message, "action": "전원연결", "action_text": "전원연결",
                "name": "박철수" if "박철수" in message else "이영희",
                "address": "울진군 OO면 OO길 78" if "박철수" in message else "광명시 OO동 OO로 56"}
    return {"message": message, "action": "기기위치조정", "action_text": "위치조정",
            "name": "이영희", "address": "광명시 OO동 OO로 56"}


@pytest.fixture(autouse=True)
def mock_model_decisions(monkeypatch):
    monkeypatch.setattr("app.automation.unified_workflow.analyze_request", lambda llm, source, cancel: model_request(source))


@pytest.mark.parametrize("message,action,name,address,reply", [
    (MESSAGE, "기기위치조정", "이영희", "광명시 OO동 OO로 56", REPLY),
    (POWER_MESSAGE, "전원연결", "박철수", "울진군 OO면 OO길 78", POWER_REPLY),
    ("위치조정/넥스터_이은경/헌릉로8길58", "기기위치조정", "넥스터_이은경", "헌릉로8길58", REPLY),
])
def test_unified_transport(message, action, name, address, reply):
    calls = []
    responses = []
    decision = {"message": message, "action": action, "name": name, "address": address,
                "action_text": "전원연결" if action == "전원연결" else "위치조정"}

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
        }
        return httpx.Response(
            200, json={**receipt(), "api_version": "1", "verified": True, "response": reply, "kakao-reply": reply}
        )

    client = UnifiedOperationsClient(
        OperationsSettings("https://nexgent.test", "admin"), "secret", httpx.MockTransport(server),
        response_observer=responses.append,
    )
    assert client.run(decision, threading.Event()).response == reply
    assert calls == ["/auth/login", "/api/me", "/api/ax768/runs"]
    assert len(responses) == 1
    assert responses[0]["http_status"] == 200
    assert responses[0]["body"]["kakao-reply"] == reply


@pytest.mark.parametrize("source,evidence,action", [
    ("헌릉로8길58 넥스터_이은경님 기기를 다른 곳으로 옮겼습니다", "기기를 다른 곳으로 옮겼습니다", "기기위치조정"),
    ("넥스터_이은경님 / 헌릉로8길58 / 전기를 다시 꽂았습니다", "전기를 다시 꽂았습니다", "전원연결"),
])
def test_model_semantic_decision_becomes_grounded_args(source, evidence, action):
    fields = {"action": action, "action_text": evidence, "name": "넥스터_이은경", "address": "헌릉로8길58"}
    assert parse_analysis(json.dumps(fields), source) == {"message": source, **fields}
    for change in ({"name": "이은경"}, {"name": "넥스터_이은"}, {"address": "헌릉로8길5"},
                   {"action_text": "없는 말"}, {"action": "information_update"}):
        with pytest.raises(IncomingAnalysisError):
            parse_analysis(json.dumps({**fields, **change}), source)
    assert parse_analysis(json.dumps(dict.fromkeys(fields)), source) is None


def test_explicit_device_request_preserves_expanded_road_address():
    address = "서울 서초구 헌릉로 8길 58 (서초더샵포레)"
    assert explicit_device_request(f"위치조정/가상인/{address}")["address"] == address


def test_analyze_request_calls_model_for_natural_wording():
    fields = {k: v for k, v in model_request(NATURAL_MESSAGE).items() if k != "message"}
    calls = []

    async def request(messages, **kwargs):
        calls.append(messages)
        assert kwargs["structured"] is True
        assert json.loads(messages[1]["content"]) == {"message": NATURAL_MESSAGE}
        return json.dumps(fields)

    async def run_operation(operation, cancel):
        return await operation()

    llm = SimpleNamespace(request=request, run_operation=run_operation)
    assert analyze_request(llm, NATURAL_MESSAGE, threading.Event()) == {
        "message": NATURAL_MESSAGE, **fields,
    }
    assert len(calls) == 1


@pytest.mark.parametrize("source,action,keyword", [
    ("위치조정/넥스터_이은경/헌릉로8길58", "기기위치조정", "위치조정"),
    ("울진군 OO면 OO길 78 / 기기 전원 연결 / 넥스터_이은경님", "전원연결", "기기 전원 연결"),
    ("넥스터_이은경/위치변경/광명시 OO동 OO로 56", "기기위치조정", "위치변경"),
])
def test_extracted_keyword_commands_need_no_further_llm(source, action, keyword):
    request = analyze_request(None, source, threading.Event())
    assert request["message"] == source and request["action_text"] == keyword
    assert request["name"] == "넥스터_이은경" and request["action"] == action


@pytest.mark.parametrize("source", [
    "위치조정/이영희/헌릉로8길58 취소합니다",
    "예시: 위치조정/이영희/헌릉로8길58",
    "이영희/헌릉로8길58/위치조정 했나요?",
    "위치조정 및 전원연결/이영희/헌릉로8길58",
])
def test_keyword_mentions_still_require_intent_check(source):
    async def request(messages, **kwargs):
        assert json.loads(messages[1]["content"]) == {"message": source}
        return json.dumps(dict.fromkeys(("action", "action_text", "name", "address")))

    async def run_operation(operation, cancel):
        return await operation()

    llm = SimpleNamespace(request=request, run_operation=run_operation)
    assert analyze_request(llm, source, threading.Event()) is None


def test_invalid_model_analysis_never_claims_or_calls_workflow(queue, monkeypatch):
    ImageReplyQueue(queue)
    journal = OperationJournal(queue)
    operations = SimpleNamespace(run=Mock())
    monkeypatch.setattr("app.automation.unified_workflow.extract_sources", lambda *a: [NATURAL_MESSAGE])
    invalid = Mock(side_effect=IncomingAnalysisError("invalid fields"))
    monkeypatch.setattr("app.automation.unified_workflow.analyze_request", invalid)
    processor = UnifiedProcessor(journal, operations)
    with pytest.raises(IncomingAnalysisError):
        processor.answer(None, IncomingMessage("incoming", NATURAL_MESSAGE), "job", threading.Event())
    operations.run.assert_not_called()
    assert journal.get("job-0:api") is None


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
    assert processor.answer(None, IncomingMessage("incoming", MESSAGE), "job", threading.Event()) == REPLY
    assert processor.answer(None, IncomingMessage("incoming", MESSAGE), "job", threading.Event()) is None
    operations.run.assert_called_once()
    assert operations.run.call_args.args[0]["message"] == MESSAGE
    assert UnifiedWorkflow.format_reply(None, REPLY) == REPLY


@pytest.mark.parametrize("kind,text", [
    ("incoming", "안녕하세요"),
    ("incoming", "이영희/광명시 OO동 OO로 56"),
    ("incoming", "정보수정/이영희/전화번호 변경"),
    ("incoming", "사진첨부/이영희/광명시 OO동 OO로 56"),
    ("incoming", "[자동 확인]\n위치조정 완료"),
    ("outgoing", MESSAGE),
    ("outgoing", POWER_MESSAGE),
    ("incoming", "[자동 확인]\n전원연결 완료"),
    ("none", MESSAGE),
    ("uncertain", MESSAGE),
])
def test_unmatched_or_nonincoming_never_calls_api(queue, monkeypatch, kind, text):
    ImageReplyQueue(queue)
    operations = SimpleNamespace(run=Mock())
    extract = Mock(return_value=[text])
    monkeypatch.setattr("app.automation.unified_workflow.extract_sources", extract)
    processor = UnifiedProcessor(OperationJournal(queue), operations)
    assert processor.answer(None, IncomingMessage(kind, text), "ignored", threading.Event()) is None
    if kind == "incoming" and not text.startswith("[자동 확인]"):
        extract.assert_called_once()
    else:
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
    assert operations.run.call_args.args[0]["message"] == message


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
    assert processor.answer(None, incoming, "job", threading.Event()) == (None if resume else REPLY)
    if resume:
        extract.assert_not_called()
        operations.run.assert_not_called()
    else:
        operations.run.assert_called_once()
        assert operations.run.call_args.args[0]["message"] == MESSAGE
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
    incoming = IncomingMessage("incoming", "\n".join(sources))
    assert processor.answer(None, incoming, "job", threading.Event()) == REPLY + "\n\n" + POWER_REPLY
    assert processor.answer(None, incoming, "job", threading.Event()) is None
    assert [call.args[0]["message"] for call in operations.run.call_args_list] == [MESSAGE, POWER_MESSAGE]


def test_two_actions_in_one_message_never_guesses(queue, monkeypatch):
    ImageReplyQueue(queue)
    message = "위치조정 및 전원연결/박철수/울진군 OO면 OO길 78"
    monkeypatch.setattr("app.automation.unified_workflow.extract_sources", lambda *a: [message])
    operations = SimpleNamespace(run=Mock())
    processor = UnifiedProcessor(OperationJournal(queue), operations)
    assert processor.answer(None, IncomingMessage("incoming", message), "job", threading.Event()) is None
    operations.run.assert_not_called()


@pytest.mark.parametrize("message", ["안녕하세요", "위치조정 및 전원연결/박철수/OO길78"])
def test_transport_rejects_unstructured_requests_before_network(message):
    calls = []
    client = UnifiedOperationsClient(
        OperationsSettings("https://nexgent.test", "admin"), "secret",
        httpx.MockTransport(lambda request: calls.append(request)),
    )
    with pytest.raises(AgentError, match="structured action"):
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
        assert processor.answer(
            None, IncomingMessage("incoming", MESSAGE), "job", threading.Event()
        ) is None
    operations.run.assert_called_once()


def test_response_validation():
    reply = "[자동 확인]\n신호 미확인. "
    body = {
        **receipt(),
        "api_version": "1",
        "verified": False,
        "status": "disconnected", "ok": False,
        "issues": [{"code": "NO_SIGNAL", "stage": "signal", "message": "신호 미확인", "next_action": "전원을 확인하세요"}],
        "response": reply,
        "kakao-reply": reply,
    }
    assert parse_unified_result(body).response == reply
    for invalid in [
        {**body, "kakao-reply": "x" * 2001},
        {"workflow_id": "information_update", "status": "completed", "response": "done"},
    ]:
        with pytest.raises(AgentError):
            parse_unified_result(invalid)


@pytest.mark.parametrize("reply", [None, "", " \n\t", [], {"text": "done"}, "x" * 2001, "bad\x00text"])
def test_device_success_uses_response_even_if_duplicate_kakao_field_is_invalid(reply):
    body = {**receipt(), "api_version": "1", "verified": True, "kakao-reply": reply}
    assert parse_unified_result(body).response == body["response"]


def test_device_success_needs_no_duplicate_kakao_reply():
    body = receipt()
    assert parse_unified_result(body).response == body["response"]


def test_power_success_with_missing_as_row_uses_exact_kakao_reply(queue):
    jobs = ImageReplyQueue(queue)
    journal = OperationJournal(queue)
    message = "이은경/헌릉로8길58/전원연결"
    reply = ("  [자동 확인]\n이은경님 기기신호 확인 완료입니다.\n\n■ 반영 영역\n"
             "AS 시트 기재 : 패스\n마스터페이지 일반사항 기재 : 완료\n\n감사합니다.\n")
    body = {
        **receipt(), "id": "f1884969-000f-4813-b9fd-d80b9a196f6a",
        "api_version": "1", "verified": True,
        "response": reply,
        "kakao-reply": reply,
        "roster": {"status": "found", "name": "이은경", "row": 4015},
        "as_lookup": {"status": "not_found"},
        "as_update": {"status": "skipped", "verified": False},
        "member_note": {"status": "already_present", "verified": True},
        "sms": {"should_send": False, "recipients": [], "title": "", "text": ""},
    }

    def server(request):
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={})
        if request.url.path == "/api/me":
            return httpx.Response(200, json={"is_admin": True, "csrf_token": "csrf"})
        assert request.url.path == "/api/ax768/runs"
        assert json.loads(request.content)["message"] == message
        return httpx.Response(200, json=body)

    client = UnifiedOperationsClient(
        OperationsSettings("https://nexgent.test", "admin"), "secret", httpx.MockTransport(server)
    )
    # Seed the analyzed request so the module's model fixture cannot substitute a different person.
    job = jobs.enqueue("chat", "capture")
    journal.claim(job + "-0:analysis", job, {"request": explicit_device_request(message)})
    processor = UnifiedProcessor(journal, client)
    incoming = IncomingMessage("incoming", message, bubbles=(message,))
    assert processor.answer(None, incoming, job, threading.Event()) == reply
    assert journal.get(job + ":reply") is None
    assert processor.answer(None, incoming, job, threading.Event()) is None


@pytest.mark.parametrize("reply", [" \t서버 응답\n", "첫째\r\n둘째\r\n"])
def test_kakao_reply_preserves_whitespace(reply):
    body = {**receipt(), "api_version": "1", "verified": True, "kakao-reply": reply}
    body["response"] = reply
    assert parse_unified_result(body).response == reply


def test_identical_new_requests_use_each_current_http_response(queue, monkeypatch):
    jobs = ImageReplyQueue(queue)
    journal = OperationJournal(queue)
    message = "이은경/헌릉로8길58/전원연결"
    replies = ["[자동 확인]\n현재 첫 번째 결과", "[자동 확인]\n현재 두 번째 결과"]
    requests = []

    def server(request):
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={}, headers={"set-cookie": "session=test; Path=/"})
        assert request.headers["cookie"] == "session=test"
        if request.url.path == "/api/me":
            return httpx.Response(200, json={"is_admin": True, "csrf_token": "csrf"})
        assert request.url.path == "/api/ax768/runs"
        assert request.headers["x-csrf-token"] == "csrf"
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            **receipt(), "api_version": "1", "verified": True,
            "response": replies[len(requests) - 1],
            "kakao-reply": replies[len(requests) - 1],
            "id": f"execution-{len(requests)}",
        })

    client = UnifiedOperationsClient(
        OperationsSettings("https://nexgent.test", "admin"), "secret", httpx.MockTransport(server)
    )
    monkeypatch.setattr("app.automation.unified_workflow.analyze_request", analyze_request)
    processor = UnifiedProcessor(journal, client)
    incoming = IncomingMessage("incoming", message, bubbles=(message,))
    for index, expected in enumerate(replies):
        job = jobs.enqueue("chat", f"capture-{index}")
        journal.claim(job + ":reply", job, "Stale saved reply")
        assert processor.answer(None, incoming, job, threading.Event()) == expected
        audit = journal.get(job + "-0:api")
        assert audit["api_response_id"] == f"execution-{index + 1}"
        assert audit["outgoing_text"] == expected
        assert audit["original_request"] == message
        restarted = UnifiedProcessor(OperationJournal(queue), client)
        assert restarted.answer(None, incoming, job, threading.Event()) is None
        assert journal.get(job + "-0:api") == audit
    assert len(requests) == 2 and requests[0] == requests[1]
    assert requests[0] == {"workflow_id": "device_adjustment_power", "message": message, "confirmed_name": None}


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
    ("incoming", " 위치조정/이은경/헌릉로8길58", True),
    ("incoming", MESSAGE, True),
    ("incoming", "기기" + MESSAGE, True),
    ("incoming", POWER_MESSAGE, True),
    ("incoming", NATURAL_MESSAGE, False),
    ("incoming", "안녕하세요", False),
    ("incoming", "정보수정/이영희/전화번호 변경", False),
    ("outgoing", MESSAGE, False),
    ("outgoing", POWER_MESSAGE, False),
    ("incoming", "[자동 확인]\n" + MESSAGE, False),
])
@pytest.mark.parametrize("startup", [False, True])
@pytest.mark.parametrize("status", ["completed", "not_found"])
def test_screenshot_to_api_reply_keeps_watching(watching, monkeypatch, kind, text, should_act, startup, status):  # noqa: F811
    from tests.test_queued_visual_catch import changed, finish

    monkeypatch.setattr("app.automation.unified_workflow.analyze_request", analyze_request)
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
    if status == "not_found":
        name = (model_request(text) or {}).get("name", "이영희")
        reply = (
            f"[자동 확인]\n{name}님 신규설치 기기신호가 아직 확인되지 않습니다.\n"
            "기기 전원 및 설치 위치 확인 부탁드립니다. "
        )
    operations = SimpleNamespace(run=Mock(return_value=OperationsResult(status, reply, status == "completed")))
    unified.processor_factory = lambda: UnifiedProcessor(unified.journal, operations)
    w.llm.classify = lambda *a, **kw: IncomingMessage(kind, text)
    w.llm.classify_latest = Mock(return_value=IncomingMessage(kind, text) if startup else IncomingMessage("none"))

    async def request(messages, **kwargs):
        data = json.loads(messages[1]["content"])
        if "text" in data:
            assert data["text"] == text
            return json.dumps({"requests": [text]})
        assert data["message"] == text
        result = model_request(text) if should_act else None
        return json.dumps({k: result[k] if result else None for k in ("action", "action_text", "name", "address")})

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
    unified.screening.result(timeout=2)
    w.service.command("stop")
    w.service.dispatch(w.service.commands.get_nowait())
    w.service.dispatch("auto_catch")
    unified.sender.send.assert_not_called()
    operations.run.assert_not_called()
    # Startup analysis requires no screen change. Later captures still use pairs.
    w.service.poll_auto_catch()
    finish(w)
    if not startup:
        changed(w, 30)
        finish(w)
    assert unified.active
    assert unified.jobs.count(unified.chat_key) == 0
    if should_act:
        assert w.sent == [reply]
        unified.sender.send.assert_called_once_with(reply, require_empty=False)
        operations.run.assert_called_once()
        assert operations.run.call_args.args[0]["message"] == text
    else:
        assert w.sent == []
        unified.sender.send.assert_not_called()
        operations.run.assert_not_called()
    assert w.llm.classify_latest.call_count == 2

    # Each click extracts the latest visible message again, even on the identical screen.
    w.service.command("stop")
    w.service.dispatch(w.service.commands.get_nowait())
    w.service.dispatch("auto_catch")
    w.service.poll_auto_catch()
    finish(w)
    assert len(w.sent) == (int(should_act) * (2 if startup else 1))
    assert w.llm.classify_latest.call_count == 3


def test_reset_discards_only_selected_unfinished_jobs_and_keeps_delivery_history(queue):
    jobs = ImageReplyQueue(queue)
    previous = [jobs.enqueue_pair("chat", b"before", bytes([i]))[0] for i in range(5)]
    assert jobs.claim("chat")["job_id"] == previous[0]
    for job_id, status in zip(previous[2:], ("sending", "review", "sent"), strict=True):
        jobs.finish(job_id, status)
    other, _ = jobs.enqueue_pair("other", b"other", b"other")
    assert jobs.reset_for_run("chat") == 2
    assert jobs.count("chat") == 0 and jobs.claim("chat") is None
    assert jobs.review_count("chat") == 0
    assert jobs.claim("other")["job_id"] == other
    with queue.connect() as db:
        assert [row[0] for row in db.execute(
            "SELECT status FROM image_reply_queue WHERE chat_key='chat' ORDER BY id"
        )] == ["ignored", "ignored", "archived_review", "archived_review", "sent"]
    # Reopening storage must not reactivate archived attempts or lose evidence.
    reopened = ImageReplyQueue(queue)
    assert reopened.review_count("chat") == 0
    with queue.connect() as db:
        archived = dict(db.execute(
            "SELECT * FROM image_reply_queue WHERE job_id=?", (previous[2],)
        ).fetchone())
    assert reopened.load_images(archived) == [b"before", bytes([2])]


def test_startup_snapshot_mode_and_pending_identity_survive_restart(queue):
    jobs = ImageReplyQueue(queue)
    job_id, _ = jobs.enqueue_pair("chat", b"snapshot", b"snapshot", mode="latest")
    jobs.claim("chat")
    reopened = ImageReplyQueue(queue)
    assert reopened.enqueue_pair("chat", b"snapshot", b"snapshot", mode="latest")[0] == job_id
    job = reopened.claim("chat")
    assert job["job_id"] == job_id
    assert json.loads(job["text"])["mode"] == "latest"
    assert reopened.load_images(job) == [b"snapshot", b"snapshot"]


def test_future_workflow_uses_common_verified_envelope():
    body = {
        "api_version": "1",
        "workflow_id": "future_workflow",
        "status": "completed",
        "verified": True,
        "response": "[자동 확인]\n서버에서 검증한 결과",
        "kakao-reply": "[자동 확인]\n서버에서 검증한 결과",
        "id": "future-run", "ok": True, "issues": [],
        "sms": {"should_send": False, "recipients": [], "title": "", "text": ""},
    }
    result = parse_unified_result(body)
    assert result.completed and result.response == body["kakao-reply"]
    for change in [{"api_version": "2"}, {"verified": False}, {"workflow_id": "../other"}]:
        with pytest.raises(AgentError):
            parse_unified_result({**body, **change})

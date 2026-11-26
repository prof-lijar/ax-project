import json
import threading
from types import SimpleNamespace

import httpx
import pytest

from app.api.device_request import CLARIFY, parse_requests
from app.api.incoming_llm import IncomingAnalysisError, IncomingMessage
from app.api.operations_client import (
    ASSISTANT_ID,
    OperationsClient,
    OperationsResult,
    OperationsSettings,
    parse_result,
)
from app.automation.device_workflow import UNCERTAIN, DeviceProcessor
from app.models import AgentError, Cancelled
from app.storage.image_reply_queue import ImageReplyQueue
from app.storage.operation_journal import OperationJournal
from tests.test_queued_visual_catch import changed, finish, watching  # noqa: F401


@pytest.fixture(autouse=True)
def forbid_device_sms(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Device location/power workflows must never create or send Bizgo SMS")

    monkeypatch.setattr("app.api.bizgo_client.create_bizgo", forbidden)
    monkeypatch.setattr("app.api.bizgo_client.BizgoClient.send", forbidden)


def receipt():
    return {
        "workflow_id": "device_adjustment_power",
        "status": "completed",
        "response": "기기 신호 확인 및 운영시트 처리 완료",
        "signal": {"status": "connected", "connected": True, "fresh": True},
        "as_lookup": {"status": "found"},
        "as_update": {"status": "updated", "verified": True},
        "member_note": {"status": "saved", "verified": True},
    }


def test_authenticated_api_contract_and_receipts():
    calls = []

    def server(request):
        calls.append(request.url.path)
        if request.url.path == "/auth/login":
            assert request.headers["origin"] == "https://nexgent.test"
            assert json.loads(request.content) == {"username": "admin", "password": "secret"}
            return httpx.Response(
                200,
                json={"authenticated": True},
                headers={"set-cookie": "session=test; Path=/; Secure; HttpOnly"},
            )
        assert request.headers["cookie"] == "session=test"
        if request.url.path == "/api/me":
            return httpx.Response(200, json={"is_admin": True, "csrf_token": "csrf"})
        if request.url.path.endswith("/schemas"):
            return httpx.Response(
                200,
                json={"input_schema": {"properties": {"member_note_mode": {"const": "prepend"}}}},
            )
        assert request.url.path == "/api/ax768/workflow/runs"
        assert (
            request.headers["origin"] == "https://nexgent.test"
            and request.headers["x-csrf-token"] == "csrf"
        )
        assert json.loads(request.content) == {
            "workflow_id": "device_adjustment_power",
            "message": "헌릉로8길58 이은경님 기기위치조정 신호확인요.",
            "confirmed_name": None,
        }
        return httpx.Response(200, json=receipt())

    client = OperationsClient(
        OperationsSettings("https://nexgent.test", "admin"), "secret", httpx.MockTransport(server)
    )
    result = client.run("헌릉로8길58 이은경님 기기위치조정 신호확인요.", threading.Event())
    assert result.completed
    assert calls == [
        "/auth/login",
        "/api/me",
        f"/agent-server/assistants/{ASSISTANT_ID}/schemas",
        "/api/ax768/workflow/runs",
    ]


@pytest.mark.parametrize(
    "failure", ["login", "permission", "redirect", "timeout", "oversize", "invalid"]
)
def test_api_failures_never_retry_or_forward_credentials(failure):
    calls = []

    def server(request):
        calls.append(request.url.path)
        if failure == "login":
            return httpx.Response(401, json={"secret": "do not expose"})
        if failure == "redirect":
            return httpx.Response(307, headers={"location": "https://other.test"})
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={})
        if request.url.path == "/api/me":
            return httpx.Response(
                200, json={"is_admin": failure != "permission", "csrf_token": "csrf"}
            )
        if request.url.path.endswith("/schemas"):
            return httpx.Response(
                200,
                json={"input_schema": {"properties": {"member_note_mode": {"const": "prepend"}}}},
            )
        if failure == "timeout":
            raise httpx.ReadTimeout("private response")
        if failure == "oversize":
            return httpx.Response(200, content=b"x" * 1_000_001)
        return httpx.Response(200, json={"status": "completed"})

    client = OperationsClient(
        OperationsSettings("https://nexgent.test", "admin"), "secret", httpx.MockTransport(server)
    )
    with pytest.raises(AgentError) as error:
        client.run("test", threading.Event())
    assert "secret" not in str(error.value) and "private" not in str(error.value)
    assert calls.count("/api/ax768/workflow/runs") <= 1
    assert len(calls) == len(set(calls))


@pytest.mark.parametrize("field", ["signal", "as_update", "member_note"])
def test_unverified_completion_is_rejected(field):
    body = receipt()
    body[field] = {}
    with pytest.raises(AgentError):
        parse_result(body)


def test_api_cancellation_stops_before_workflow_post():
    cancel = threading.Event()
    calls = []

    def server(request):
        calls.append(request.url.path)
        cancel.set()
        return httpx.Response(200, json={})

    client = OperationsClient(
        OperationsSettings("https://nexgent.test", "admin"), "secret", httpx.MockTransport(server)
    )
    with pytest.raises((Cancelled, AgentError)):
        client.run("test", cancel)
    assert "/api/ax768/workflow/runs" not in calls


def encoded(
    name="이은경",
    address="헌릉로8길58",
    action="기기위치조정",
    source="이은경/위치변경/헌릉로8길58",
):
    return json.dumps(
        {"requests": [{"name": name, "address": address, "action": action, "source": source}]},
        ensure_ascii=False,
    )


def test_extractor_preserves_explicit_source_and_alias():
    incoming = IncomingMessage("incoming", "이은경/위치변경/헌릉로8길58", "관리자")
    assert parse_requests(encoded(), incoming) == [
        {"name": "이은경", "address": "헌릉로8길58", "action": "기기위치조정"}
    ]
    for value in (
        encoded(name="다른사람"),
        encoded(address="서울"),
        encoded(action="전원연결"),
        encoded(source="다른 내용"),
        "{}",
    ):
        with pytest.raises(IncomingAnalysisError):
            parse_requests(value, incoming)


def test_unrelated_text_has_clarification_plan():
    incoming = IncomingMessage("incoming", "안녕하세요")
    plan = parse_requests(encoded("", "", "", "안녕하세요"), incoming)
    assert plan == [{"name": "", "address": "", "action": ""}]


@pytest.fixture
def processor(queue, monkeypatch):
    jobs = ImageReplyQueue(queue)
    job_id = jobs.enqueue("device-chat", "screenshots")
    stages = []
    api = SimpleNamespace(
        run=lambda message, cancel: (
            stages.append(("api", message)) or OperationsResult("completed", "처리 완료", True)
        )
    )
    engine = DeviceProcessor(OperationJournal(queue), api)
    plan = [{"name": "이은경", "address": "헌릉로8길58", "action": "기기위치조정"}]
    monkeypatch.setattr("app.automation.device_workflow.extract_requests", lambda *a: plan)
    return SimpleNamespace(
        engine=engine,
        stages=stages,
        job_id=job_id,
        jobs=jobs,
        queue=queue,
        api=api,
        plan=plan,
        incoming=IncomingMessage("incoming", "이은경/위치변경/헌릉로8길58"),
        cancel=threading.Event(),
    )


@pytest.mark.parametrize(
    "action, wording", [("기기위치조정", "기기 위치변경"), ("전원연결", "전원연결")]
)
def test_pipeline_and_resume_only_call_api_without_sms(processor, action, wording):
    p = processor
    p.plan[0]["action"] = action
    reply = p.engine.answer(None, p.incoming, p.job_id, p.cancel)
    assert reply == (
        f"[자동 확인]\n이은경님 {wording} 후 기기신호 확인 완료입니다.\n"
        "내용 기재해두었습니다.\n감사합니다. :)"
    )
    assert [kind for kind, _ in p.stages] == ["api"]
    assert p.engine.journal.get(p.job_id + "-0:sms") is None
    restarted = DeviceProcessor(OperationJournal(p.queue), p.api)
    assert restarted.answer(None, p.incoming, p.job_id, p.cancel) == reply
    assert len(p.stages) == 1


@pytest.mark.parametrize("missing", ["action", "name", "address"])
def test_missing_fields_ask_and_never_execute(processor, missing):
    p = processor
    p.plan[0][missing] = ""
    assert CLARIFY in p.engine.answer(None, p.incoming, p.job_id, p.cancel)
    assert not p.stages


@pytest.mark.parametrize(
    "status", ["disconnected", "not_found", "needs_confirmation", "blocked", "failed"]
)
def test_noncompletion_replies_honestly_without_success_sms(processor, status):
    p = processor
    p.api.run = lambda *a: OperationsResult(status, "대상자 주소를 확인해주세요", False)
    assert "주소를 확인" in p.engine.answer(None, p.incoming, p.job_id, p.cancel)
    assert not p.stages


def test_uncertain_api_never_retries_and_later_job_runs(processor):
    p = processor
    api = p.api.run

    def failing(*a):
        p.stages.append(("api", "attempt"))
        raise AgentError("timeout")

    p.api.run = failing
    assert UNCERTAIN in p.engine.answer(None, p.incoming, p.job_id, p.cancel)
    assert UNCERTAIN in p.engine.answer(None, p.incoming, p.job_id, p.cancel)
    assert len(p.stages) == 1
    p.api.run = api
    next_job = p.jobs.enqueue("device-chat", "next")
    assert "기기신호 확인 완료" in p.engine.answer(None, p.incoming, next_job, p.cancel)
    assert [kind for kind, _ in p.stages] == ["api", "api"]


def test_old_sms_receipt_is_not_retried_or_changed(processor):
    p = processor
    sms_key = p.job_id + "-0:sms"
    p.engine.journal.claim(sms_key, p.job_id, "Old uncertain SMS receipt")
    reply = p.engine.answer(None, p.incoming, p.job_id, p.cancel)
    assert "기기신호 확인 완료" in reply and "Bizgo" not in reply
    assert p.engine.journal.get(sms_key) == "Old uncertain SMS receipt"
    assert p.engine.answer(None, p.incoming, p.job_id, p.cancel) == reply
    assert len(p.stages) == 1


def test_stop_during_external_action_resumes_without_duplicate(processor):
    p = processor

    def stop(*a):
        p.stages.append(("api", "attempt"))
        p.cancel.set()
        raise Cancelled("stopped")

    p.api.run = stop
    with pytest.raises(Cancelled):
        p.engine.answer(None, p.incoming, p.job_id, p.cancel)
    p.cancel.clear()
    restarted = DeviceProcessor(OperationJournal(p.queue), p.api)
    reply = restarted.answer(None, p.incoming, p.job_id, p.cancel)
    assert UNCERTAIN in reply
    assert "기기신호 확인 완료" not in reply
    assert [kind for kind, _ in p.stages] == ["api"]


def test_multiple_requests_in_one_capture_are_processed_in_order(processor):
    p = processor
    p.plan.append({"name": "김순옥", "address": "울진북로164", "action": "전원연결"})
    reply = p.engine.answer(None, p.incoming, p.job_id, p.cancel)
    assert "1. " in reply and "2. " in reply
    assert "1. 이은경님 기기 위치변경 후 기기신호 확인 완료입니다." in reply
    assert "2. 김순옥님 전원연결 후 기기신호 확인 완료입니다." in reply
    assert [kind for kind, _ in p.stages] == ["api", "api"]
    assert p.stages[1][1] == "울진북로164 김순옥님 전원연결 신호확인요."


def test_device_mode_queues_while_api_runs_then_replies_and_continues(watching, monkeypatch):  # noqa: F811
    w = watching
    w.service.command("stop")
    w.service.dispatch(w.service.commands.get_nowait())
    device = w.service.device_workflow
    device.clock = lambda: w.now[0]
    device.llm_factory = lambda _: w.llm
    device.sender = w.sender
    classify = w.llm.classify

    def power_message(*args, **kwargs):
        item = classify(*args, **kwargs)
        return IncomingMessage(item.kind, item.text + " / 전원연결")

    w.llm.classify = power_message
    stages, entered, release = [], threading.Event(), threading.Event()
    monkeypatch.setattr(
        "app.automation.device_workflow.extract_requests",
        lambda llm, incoming, cancel: [
            {"name": incoming.text.split(" / ")[0], "address": "테스트로1", "action": "전원연결"}
        ],
    )

    def api(message, cancel):
        stages.append(("api", message))
        entered.set()
        assert release.wait(2)
        return OperationsResult("completed", message + " 처리 완료", True)

    device.processor_factory = lambda: DeviceProcessor(
        device.journal, SimpleNamespace(run=api)
    )
    w.service.dispatch("device_workflow")
    assert w.service.auto_catch is device
    assert device.chat_key != w.workflow.queue_key()
    w.workflow = device
    changed(w, 30)
    assert entered.wait(2)
    changed(w, 60)
    changed(w, 90)
    assert device.jobs.count(device.chat_key) == 3
    release.set()
    finish(w)
    w.now[0] += 4
    finish(w)
    finish(w)
    w.now[0] += 4
    finish(w)
    finish(w)
    assert [kind for kind, _ in stages] == ["api", "api", "api"]
    assert device.reply_count == 3
    assert all(any(f"Question {n}" in reply for reply in w.sent) for n in (30, 60, 90))
    for n in (30, 60, 90):
        assert (
            f"[자동 확인]\nQuestion {n}님 전원연결 후 기기신호 확인 완료입니다.\n"
            "내용 기재해두었습니다.\n감사합니다. :)"
        ) in w.sent
    assert device.jobs.count(device.chat_key) == 0
    w.service.command("stop")
    device.reset()


def test_structured_llm_request_extracts_without_generic_answer():
    from app.api.device_request import extract_requests
    from app.api.incoming_llm import IncomingLLM
    from app.api.workflow_llm import LLMSettings

    calls = []

    def server(request):
        payload = json.loads(request.content)
        assert payload["response_format"] == {"type": "json_object"}
        calls.append(payload["messages"])
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": encoded()}}]}
        )

    llm = IncomingLLM(
        LLMSettings("https://llm.test/v1/chat/completions", "configured-model", 5),
        "synthetic-key",
        httpx.MockTransport(server),
    )
    result = extract_requests(
        llm, IncomingMessage("incoming", "이은경/위치변경/헌릉로8길58"), threading.Event()
    )
    assert result[0]["action"] == "기기위치조정" and len(calls) == 1


def test_ambiguous_action_and_unsupported_name_request_clarification():
    text = "이은경/기기위치조정 또는 전원연결"
    plan = parse_requests(
        encoded("이은경", "", "전원연결", text), IncomingMessage("incoming", text)
    )
    assert not plan[0]["action"]
    text = "관리자123 전원연결"
    plan = parse_requests(
        encoded("관리자123", "", "전원연결", text), IncomingMessage("incoming", text)
    )
    assert not plan[0]["name"]


def test_device_destination_settings_isolate_retained_jobs(watching):  # noqa: F811
    device = watching.service.device_workflow
    original = device.queue_key()
    for field, value in [
        ("operations_url", "https://other.test"),
        ("operations_username", "another"),
        ("bizgo_recipient", "01011112222"),
        ("bizgo_sandbox", False),
    ]:
        before = getattr(device.config, field)
        setattr(device.config, field, value)
        assert device.queue_key() != original
        setattr(device.config, field, before)
    assert device.queue_key() == original


def test_device_processor_starts_without_bizgo_settings(watching, monkeypatch):  # noqa: F811
    device = watching.service.device_workflow
    device.config.bizgo_enabled = True
    device.config.bizgo_sandbox = False
    device.config.bizgo_sender = device.config.bizgo_recipient = ""
    operations = SimpleNamespace(run=lambda *a: None)
    monkeypatch.setattr("app.automation.device_workflow.create_operations", lambda _: operations)
    assert device.processor_factory().operations is operations


@pytest.mark.parametrize("mode", [None, "replace", "append"])
def test_old_server_cannot_execute_replacing_workflow(mode):
    calls = []

    def server(request):
        calls.append(request.url.path)
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={})
        if request.url.path == "/api/me":
            return httpx.Response(200, json={"is_admin": True, "csrf_token": "csrf"})
        assert request.url.path.endswith("/schemas")
        return httpx.Response(
            200, json={"input_schema": {"properties": {"member_note_mode": {"const": mode}}}}
        )

    client = OperationsClient(
        OperationsSettings("https://nexgent.test", "admin"), "secret", httpx.MockTransport(server)
    )
    with pytest.raises(AgentError, match="no workflow executed"):
        client.run("테스트로1 이은경님 전원연결 신호확인요.", threading.Event())
    assert "/api/ax768/workflow/runs" not in calls

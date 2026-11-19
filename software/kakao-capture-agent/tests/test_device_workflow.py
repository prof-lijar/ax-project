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
from app.automation.device_workflow import SMS_UNCERTAIN, UNCERTAIN, DeviceProcessor
from app.models import AgentError, Cancelled
from app.storage.image_reply_queue import ImageReplyQueue
from app.storage.operation_journal import OperationJournal
from tests.test_queued_visual_catch import changed, finish, watching  # noqa: F401


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
                json={"input_schema": {"properties": {"member_note_mode": {"const": "append"}}}},
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
                json={"input_schema": {"properties": {"member_note_mode": {"const": "append"}}}},
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
    bizgo = SimpleNamespace(
        settings=SimpleNamespace(sandbox=False),
        prepare=lambda text, reference: (text, reference),
        send=lambda message, cancel: stages.append(("sms", message)) or "accepted",
    )
    engine = DeviceProcessor(OperationJournal(queue), api, bizgo)
    plan = [{"name": "이은경", "address": "헌릉로8길58", "action": "기기위치조정"}]
    monkeypatch.setattr("app.automation.device_workflow.extract_requests", lambda *a: plan)
    return SimpleNamespace(
        engine=engine,
        stages=stages,
        job_id=job_id,
        jobs=jobs,
        queue=queue,
        api=api,
        bizgo=bizgo,
        plan=plan,
        incoming=IncomingMessage("incoming", "이은경/위치변경/헌릉로8길58"),
        cancel=threading.Event(),
    )


def test_pipeline_order_and_resume_does_not_repeat_api_or_sms(processor):
    p = processor
    reply = p.engine.answer(None, p.incoming, p.job_id, p.cancel)
    assert reply.startswith("[AI] 처리 완료") and "문자 접수 완료" in reply
    assert [kind for kind, _ in p.stages] == ["api", "sms"]
    assert p.stages[1][1][0] == "[test] 기기위치조정/전원연결 처리 성공"
    restarted = DeviceProcessor(OperationJournal(p.queue), p.api, p.bizgo)
    assert restarted.answer(None, p.incoming, p.job_id, p.cancel) == reply
    assert len(p.stages) == 2


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
    assert "처리 완료" in p.engine.answer(None, p.incoming, next_job, p.cancel)
    assert [kind for kind, _ in p.stages] == ["api", "api", "sms"]


def test_sms_failure_keeps_api_result_and_does_not_resend(processor):
    p = processor

    def failing(*a):
        p.stages.append(("sms", "attempt"))
        raise AgentError("timeout")

    p.bizgo.send = failing
    reply = p.engine.answer(None, p.incoming, p.job_id, p.cancel)
    assert "처리 완료" in reply and SMS_UNCERTAIN in reply
    assert p.engine.answer(None, p.incoming, p.job_id, p.cancel) == reply
    assert len(p.stages) == 2


@pytest.mark.parametrize("stage", ["api", "sms"])
def test_stop_during_external_action_resumes_without_duplicate(processor, stage):
    p = processor

    def stop(*a):
        p.stages.append((stage, "attempt"))
        p.cancel.set()
        raise Cancelled("stopped")

    if stage == "api":
        p.api.run = stop
    else:
        p.bizgo.send = stop
    with pytest.raises(Cancelled):
        p.engine.answer(None, p.incoming, p.job_id, p.cancel)
    p.cancel.clear()
    restarted = DeviceProcessor(OperationJournal(p.queue), p.api, p.bizgo)
    reply = restarted.answer(None, p.incoming, p.job_id, p.cancel)
    assert (UNCERTAIN if stage == "api" else SMS_UNCERTAIN) in reply
    assert [kind for kind, _ in p.stages].count(stage) == 1


def test_multiple_requests_in_one_capture_are_processed_in_order(processor):
    p = processor
    p.plan.append({"name": "김순옥", "address": "울진북로164", "action": "전원연결"})
    reply = p.engine.answer(None, p.incoming, p.job_id, p.cancel)
    assert "1. " in reply and "2. " in reply
    assert [kind for kind, _ in p.stages] == ["api", "sms", "api", "sms"]
    assert p.stages[2][1] == "울진북로164 김순옥님 전원연결 신호확인요."
    assert p.stages[1][1][1] != p.stages[3][1][1]


def test_device_mode_queues_while_api_runs_then_replies_and_continues(watching, monkeypatch):  # noqa: F811
    w = watching
    w.service.command("stop")
    w.service.dispatch(w.service.commands.get_nowait())
    device = w.service.device_workflow
    device.clock = lambda: w.now[0]
    device.llm_factory = lambda _: w.llm
    device.sender = w.sender
    stages, entered, release = [], threading.Event(), threading.Event()
    monkeypatch.setattr(
        "app.automation.device_workflow.extract_requests",
        lambda llm, incoming, cancel: [
            {"name": incoming.text, "address": "테스트로1", "action": "전원연결"}
        ],
    )

    def api(message, cancel):
        stages.append(("api", message))
        entered.set()
        assert release.wait(2)
        return OperationsResult("completed", message + " 처리 완료", True)

    bizgo = SimpleNamespace(
        settings=SimpleNamespace(sandbox=False),
        prepare=lambda text, ref: ref,
        send=lambda message, cancel: stages.append(("sms", message)),
    )
    device.processor_factory = lambda: DeviceProcessor(
        device.journal, SimpleNamespace(run=api), bizgo
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
    assert [kind for kind, _ in stages] == ["api", "sms", "api", "sms", "api", "sms"]
    assert device.reply_count == 3
    assert all(any(f"Question {n}" in reply for reply in w.sent) for n in (30, 60, 90))
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


@pytest.mark.parametrize("mode", [None, "replace"])
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

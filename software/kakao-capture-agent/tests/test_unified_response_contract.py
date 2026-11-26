"""Contract and delivery correlation across real client/processor boundaries."""

import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from app.api.incoming_llm import IncomingMessage
from app.api.operations_client import OperationsSettings
from app.api.unified_operations import UnifiedOperationsClient, parse_unified_result
from app.automation.installation_sms import SMS_UNCERTAIN, InstallationSMS
from app.automation.unified_workflow import UnifiedProcessor, UnifiedWorkflow
from app.models import AgentError
from app.storage.image_reply_queue import ImageReplyQueue
from app.storage.operation_journal import OperationJournal
from tests.test_device_workflow import receipt
from tests.test_new_installation import FORM, GUARDIAN_NOTICE, result
from tests.test_queued_visual_catch import finish, watching  # noqa: F401

MESSAGE = "이은경/헌릉로8길58/전원연결"
FAILURES = ["not_found", "needs_confirmation", "disconnected", "blocked", "failed"]
WORKFLOWS = [
    "device_adjustment_power", "information_update", "device_replacement", "device_collection",
    "device_loss", "installation_confirmation", "fault_confirmation", "new_installation",
]
PARTIAL = ("[자동 확인]\n일부 작업을 완료하지 못했습니다.\n\n■ 확인 필요\n"
           "저장 결과를 확인하지 못했습니다. 다시 요청하기 전에 마스터페이지를 확인해 주세요.\n\n"
           "■ 처리 결과\n가입자 명부 시트 수정 : 완료\n마스터페이지 정보 수정 : 저장 여부 미확인")


def envelope(status="completed", workflow="device_adjustment_power"):
    completed = status == "completed"
    reply = "  [자동 확인]\n이은경님 처리 완료입니다.\n" if completed else PARTIAL
    return {
        **receipt(), "id": "execution-123", "workflow_id": workflow,
        "status": status, "ok": completed, "verified": completed,
        "response": reply, "kakao-reply": reply,
        "issues": [] if completed else [{
            "code": "SAVE_UNVERIFIED", "stage": "member", "message": "저장 여부 미확인",
            "next_action": "마스터페이지를 확인해 주세요.",
        }],
    }


def client_for(body, requests=None):
    def server(request):
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={})
        if request.url.path == "/api/me":
            return httpx.Response(200, json={"is_admin": True, "csrf_token": "csrf"})
        assert request.url.path == "/api/ax768/runs"
        if requests is not None:
            requests.append(json.loads(request.content))
        return httpx.Response(200, json=body)

    return UnifiedOperationsClient(
        OperationsSettings("https://nexgent.test", "admin"), "test", httpx.MockTransport(server)
    )


@pytest.mark.parametrize("workflow", WORKFLOWS)
@pytest.mark.parametrize("status", FAILURES)
def test_business_failures_preserve_server_text_and_issues(workflow, status):
    body = envelope(status, workflow)
    parsed = parse_unified_result(body)
    assert parsed.status == status and not parsed.completed
    assert parsed.response == body["response"] == body["kakao-reply"]
    assert parsed.api_response == body
    body["issues"][0]["message"] = "mutated after parsing"
    assert parsed.api_response["issues"][0]["message"] == "저장 여부 미확인"


@pytest.mark.parametrize("status", ["completed", *FAILURES])
@pytest.mark.parametrize("field", ["ok", "verified"])
@pytest.mark.parametrize("value", [None, 0, 1, "true", "false", "opposite"])
def test_inconsistent_flags_are_rejected(status, field, value):
    body = envelope(status, "future_workflow")
    body[field] = status != "completed" if value == "opposite" else value
    with pytest.raises(AgentError, match="contract"):
        parse_unified_result(body)


@pytest.mark.parametrize("change", [
    {"response": ""}, {"response": None}, {"response": "bad\x00text"},
    {"response": "x" * 2001}, {"response": {}}, {"ok": "true"},
    {"sms": {"should_send": True}},
])
def test_malformed_envelope_never_produces_a_reply(change, queue):
    ImageReplyQueue(queue)
    logs = []
    journal = OperationJournal(queue)
    processor = UnifiedProcessor(journal, client_for({**envelope(), **change}), logs.append)
    assert processor.answer(None, IncomingMessage("incoming", MESSAGE, bubbles=(MESSAGE,)),
                            "job", threading.Event()) is None
    audit = journal.get("job-0:api")
    assert audit["status"] == "uncertain" and audit["send_outcome"] == "not_attempted"
    assert audit["outgoing_text"] is None and audit["original_request"] == MESSAGE
    assert any("result unavailable" in log for log in logs)


@pytest.mark.parametrize("field", ["id", "ok", "verified", "response", "kakao-reply", "issues", "sms"])
def test_required_envelope_fields_cannot_be_omitted(field):
    body = envelope(workflow="future_workflow")
    del body[field]
    with pytest.raises(AgentError):
        parse_unified_result(body)


@pytest.mark.parametrize("issues", [[], None, [{}], [{"code": "FAILED"}]])
def test_failure_requires_structured_issues(issues):
    with pytest.raises(AgentError, match="issues"):
        parse_unified_result({**envelope("failed"), "issues": issues})


def test_fault_workflow_can_complete_with_disconnected_signal():
    body = envelope(workflow="fault_confirmation")
    body["signal"] = {"status": "disconnected", "connected": False}
    assert parse_unified_result(body).completed


@pytest.mark.parametrize("status", ["completed", "failed"])
@pytest.mark.parametrize("delivery", ["cleared", "unconfirmed", "refused", "exception"])
def test_http_execution_is_linked_to_exact_sent_text_and_observation(watching, status, delivery):  # noqa: F811
    w = watching
    w.service.command("stop")
    w.service.dispatch(w.service.commands.get_nowait())
    body = envelope(status)
    requests = []
    client = client_for(body, requests)
    flow = UnifiedWorkflow(w.desktop, w.capture, w.queue, w.service.config, w.sender,
                           w.service.stop_input, lambda _: None, w.logs.append, activity=w.logs.append)
    flow.processor_factory = lambda: UnifiedProcessor(flow.journal, client, w.logs.append)
    flow.llm_factory = lambda _: SimpleNamespace(
        classify_latest=lambda *a: IncomingMessage("incoming", MESSAGE, bubbles=(MESSAGE,))
    )
    flow.clock = lambda: w.now[0]
    w.workflow = w.service.auto_catch = w.service.general_auto_catch = flow
    w.sender.composer_cleared = delivery == "cleared"
    w.sender.input_started = delivery != "refused"

    def send(text, **kwargs):
        # The exact text and execution identity must be durable before any input.
        with w.queue.connect() as db:
            row = db.execute("SELECT payload FROM operation_journal WHERE key LIKE '%:api'").fetchone()
        audit = json.loads(row["payload"])
        assert audit["send_outcome"] == "submitting"
        assert audit["outgoing_text"] == text == body["response"]
        assert audit["api_response_id"] == body["id"]
        if delivery in {"refused", "exception"}:
            raise AgentError("Synthetic composer failure")
        return w.send(text, **kwargs)

    w.sender.send = send
    w.service.dispatch("auto_catch")
    if delivery in {"refused", "exception"}:
        with pytest.raises(AgentError, match="Synthetic composer failure"):
            w.service.poll_auto_catch()
            finish(w)
    else:
        w.service.poll_auto_catch()
        finish(w)
    with w.queue.connect() as db:
        row = db.execute("SELECT job_id,payload FROM operation_journal WHERE key LIKE '%:api'").fetchone()
    audit = json.loads(row["payload"])
    assert audit["job_id"] == row["job_id"]
    assert audit["original_request"] == audit["request"]["message"] == MESSAGE
    assert audit["api_response_id"] == body["id"]
    assert audit["status"] == status and audit["api_response"] == body
    assert audit["outgoing_text"] == body["response"]
    assert audit["send_outcome"] == {
        "cleared": "composer_cleared", "unconfirmed": "submitted_unconfirmed",
        "refused": "not_attempted", "exception": "uncertain",
    }[delivery]
    assert len(requests) == 1
    assert requests[0] == {"workflow_id": "device_adjustment_power", "message": MESSAGE,
                           "confirmed_name": None}
    assert w.sent == ([] if delivery in {"refused", "exception"} else [body["response"]])


def test_delivery_audit_does_not_relabel_skipped_execution_on_resume(queue):
    jobs = ImageReplyQueue(queue)
    journal = OperationJournal(queue)
    job = jobs.enqueue("chat", "capture")
    journal.claim(job + ":plan", job, [MESSAGE, MESSAGE])
    old = {"response": "old reply", "api_response_id": "old-run", "send_outcome": "uncertain"}
    journal.claim(job + "-0:api", job, old)
    processor = UnifiedProcessor(journal, client_for(envelope()))
    reply = processor.answer(None, IncomingMessage("incoming", MESSAGE), job, threading.Event())
    journal.record_send(job, "composer_cleared", outgoing_text=reply)
    assert journal.get(job + "-0:api") == old
    current = journal.get(job + "-1:api")
    assert current["api_response_id"] == "execution-123"
    assert current["outgoing_text"] == reply and current["send_outcome"] == "composer_cleared"


@pytest.mark.parametrize("length,allowed", [(2000 - len(GUARDIAN_NOTICE) - 2, True), (2000, False)])
def test_api_reply_plus_observed_sms_is_checked_before_chat_send(queue, config, monkeypatch, length, allowed):
    jobs = ImageReplyQueue(queue)
    journal = OperationJournal(queue)
    job = jobs.enqueue("chat", "capture")
    body = result()
    body["response"] = body["kakao-reply"] = "가" * length
    config.bizgo_sandbox = config.bizgo_installation_test = False
    sms = InstallationSMS(config, journal, queue.event, lambda _: None)
    bizgo = Mock()
    bizgo.prepare_installation.return_value = ["guide"]
    monkeypatch.setattr("app.automation.installation_sms.create_bizgo", lambda *a, **kw: bizgo)
    processor = UnifiedProcessor(journal, client_for(body), installation_sms=sms)
    incoming = IncomingMessage("incoming", FORM, bubbles=(FORM,))
    expected = body["response"] + "\n\n" + GUARDIAN_NOTICE
    if allowed:
        assert processor.answer(None, incoming, job, threading.Event()) == expected
    else:
        with pytest.raises(AgentError, match="composer limit"):
            processor.answer(None, incoming, job, threading.Event())
    audit = journal.get(job + "-0:api")
    assert audit["outgoing_text"] == expected
    assert audit["send_outcome"] == ("ready" if allowed else "review")
    assert audit["api_response"]["ok"] is True
    assert journal.get(job + "-0:sms")["status"] == "accepted"
    assert processor.answer(None, incoming, job, threading.Event()) is None
    assert bizgo.send.call_count == 2


def test_sms_failure_keeps_server_success_and_records_separate_outcome(queue, config, monkeypatch):
    jobs = ImageReplyQueue(queue)
    journal = OperationJournal(queue)
    job = jobs.enqueue("chat", "capture")
    config.bizgo_sandbox = config.bizgo_installation_test = False
    sms = InstallationSMS(config, journal, queue.event, lambda _: None)
    bizgo = Mock()
    bizgo.prepare_installation.return_value = ["guide"]
    bizgo.send.side_effect = ["accepted", AgentError("connection lost")]
    monkeypatch.setattr("app.automation.installation_sms.create_bizgo", lambda *a, **kw: bizgo)
    processor = UnifiedProcessor(journal, client_for(result()), installation_sms=sms)
    reply = processor.answer(None, IncomingMessage("incoming", FORM, bubbles=(FORM,)), job, threading.Event())
    assert reply == result()["response"] + "\n\n" + SMS_UNCERTAIN
    audit = journal.get(job + "-0:api")
    assert audit["api_response"]["ok"] is True and audit["status"] == "completed"
    assert journal.get(job + "-0:sms") == {"status": "uncertain", "accepted_parts": 1}

import json
import threading
from dataclasses import asdict
from unittest.mock import Mock

import httpx
import pytest

from app.api.bizgo_client import BizgoClient, BizgoSettings
from app.api.incoming_llm import IncomingMessage, parse_incoming
from app.api.operations_client import OperationsSettings
from app.api.unified_operations import UnifiedOperationsClient, parse_unified_result
from app.api.workflow_requests import installation_header
from app.automation.installation_sms import InstallationSMS
from app.automation.unified_workflow import UnifiedProcessor, UnifiedWorkflow
from app.config import load, save
from app.models import AgentError, Cancelled
from app.storage.image_reply_queue import ImageReplyQueue
from app.storage.operation_journal import OperationJournal
from tests.test_bizgo import accepted
from tests.test_queued_visual_catch import changed, finish, watching  # noqa: F401

FORM = """신규설치
관리자: 테스트
SN : 00000001
가입자: 가상인
성별: 여성
생년월일: 490101
가입자 번호: 010-0000-0001
주소: 영덕군 예시길 1
보호자 성명: 가상인
보호자 번호: 010-0000-2000
대상자와의 관계: 자녀
보호자2 성명: 예시인
보호자2 번호: 010-0000-2001
보호자2 관계: 자녀"""
GUARDIANS = ["01000002000", "01000002001"]
TEST_NUMBERS = ["01000009900", "01000009901"]
GUIDE = "《설치 안내》\n" + "가나다라마\n" * 230
OK = "[자동 확인]\n기기신호 확인 완료입니다.\n내용 기재 및 보호자님께 앱설치 문자 발송 완료했습니다.\n\n감사합니다. :)"
BLOCKED = "[자동 확인]\n기기 전원 및 설치 위치 확인 부탁드립니다. "


def result(status="completed"):
    complete = status == "completed"
    return {
        "api_version": "1",
        "workflow_id": "new_installation",
        "status": status,
        "response": "등록을 완료했습니다." if complete else "등록을 확인해 주세요.",
        "verified": complete,
        "guardian_count": 2,
        "kakao-reply": OK if complete else BLOCKED,
        "receipts": {
            k: {
                "verified": complete,
                "status": "updated" if complete else "blocked",
                "rows": [5] if complete else [],
            }
            for k in ("roster", "inventory", "member")
        },
        "sms": {
            "should_send": complete,
            "recipients": GUARDIANS.copy() if complete else [],
            "title": "안심지키미 기기 설치 안내" if complete else "",
            "text": GUIDE if complete else "",
        },
    }


def incoming(*bubbles):
    return parse_incoming(
        json.dumps({"kind": "incoming", "text": bubbles, "is_ai": False, "sender": ""}), batch=True
    )


@pytest.mark.parametrize(
    "mode,status",
    [
        ("guardian", "completed"),
        ("test", "completed"),
        ("sandbox", "completed"),
        ("test", "blocked"),
        ("guardian", "failed"),
        ("partial", "completed"),
    ],
)
@pytest.mark.parametrize("startup", [True, False])
def test_auto_registration_through_chat_reply(watching, monkeypatch, mode, status, startup):  # noqa: F811
    w = watching
    w.service.command("stop")
    w.service.dispatch(w.service.commands.get_nowait())
    c = w.service.config
    c.bizgo_sender = "01000000000"
    c.bizgo_installation_test = mode == "test"
    c.bizgo_test_recipients = "010-0000-9900, 01000009901, 01000009900"
    c.bizgo_sandbox = mode == "sandbox"
    events, sends = [], []

    def operations_api(request):
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={})
        if request.url.path == "/api/me":
            return httpx.Response(200, json={"is_admin": True, "csrf_token": "test"})
        assert request.url.path == "/api/ax768/runs"
        assert request.headers["X-CSRF-Token"] == "test"
        assert json.loads(request.content) == {"workflow_id": "new_installation", "message": FORM}
        events.append("registration")
        return httpx.Response(200, json=result(status))

    def bizgo_api(request):
        assert ("sandbox" in request.url.host) == (mode == "sandbox")
        payload = json.loads(request.content)
        sends.append(payload)
        events.append("sms")
        if mode == "partial" and payload["destinations"][0]["to"] == GUARDIANS[1]:
            raise httpx.ReadTimeout("test")
        return httpx.Response(200, json=accepted(payload))

    client = UnifiedOperationsClient(
        OperationsSettings("https://example.test", "admin"),
        "test",
        httpx.MockTransport(operations_api),
    )
    monkeypatch.setattr(
        "app.automation.unified_workflow.create_unified_operations", lambda _: client
    )

    def bizgo(config, audit, *, force):
        assert force
        return BizgoClient(
            BizgoSettings.resolve(config), "test", audit, httpx.MockTransport(bizgo_api)
        )

    monkeypatch.setattr("app.automation.installation_sms.create_bizgo", bizgo)
    flow = UnifiedWorkflow(
        w.desktop,
        w.capture,
        w.queue,
        c,
        w.sender,
        w.service.stop_input,
        lambda _: None,
        w.logs.append,
    )
    w.workflow = w.service.auto_catch = w.service.general_auto_catch = flow
    flow.llm_factory = lambda _: w.llm
    flow.clock = lambda: w.now[0]
    w.llm.classify_latest = lambda *_: (
        IncomingMessage("incoming", FORM) if startup else IncomingMessage("none")
    )
    w.llm.classify = lambda *a, **kw: incoming(FORM)

    def submit(text, **kwargs):
        events.append("kakao")
        return w.send(text, **kwargs)

    flow.sender.send = submit
    w.service.dispatch("auto_catch")
    w.service.poll_auto_catch()
    finish(w)
    if not startup:
        changed(w, 30)
        finish(w)
    assert flow.active and events[0] == "registration" and events[-1] == "kakao"
    assert events.count("registration") == events.count("kakao") == 1
    (reply,) = w.sent
    if status != "completed":
        assert reply == BLOCKED and not sends
    else:
        expected = TEST_NUMBERS if mode == "test" else GUARDIANS
        assert {p["destinations"][0]["to"] for p in sends} == set(expected)
        assert len({p["idempotencyKey"] for p in sends}) == len(sends)
        for number in expected:
            parts = [
                p["messageFlow"][0]["mms"] for p in sends if p["destinations"] == [{"to": number}]
            ]
            if mode == "partial" and number == expected[-1]:
                continue
            assert len(parts) > 1
            assert all(
                p["title"] == result()["sms"]["title"] and len(p["text"].encode("euc-kr")) <= 2000
                for p in parts
            )
            assert "".join(p["text"] for p in parts) == GUIDE
        if mode == "guardian":
            assert reply == OK
        else:
            expected_text = {
                "test": "테스트 번호로만",
                "sandbox": "샌드박스",
                "partial": "결과를 확인",
            }
            assert expected_text[mode] in reply and "발송 완료했습니다" not in reply


@pytest.mark.parametrize(
    "invalid",
    [
        {"verified": False},
        {"guardian_count": 1},
        {"kakao-reply": ""},
        {"receipts": {}},
        {"sms": {"should_send": False}},
        {"sms": {**result()["sms"], "recipients": GUARDIANS[:1] * 2}},
    ],
)
def test_invalid_installation_cannot_authorize_sms(invalid):
    with pytest.raises(AgentError):
        parse_unified_result({**result(), **invalid})


def test_contract_identity_bound_to_request():
    client = UnifiedOperationsClient(OperationsSettings("https://example.test", "admin"), "test")
    with pytest.raises(AgentError, match="different workflow"):
        client.parse_run_result(result(), {"workflow_id": "device_adjustment_power"})
    with pytest.raises(AgentError, match="different workflow"):
        client.parse_run_result(
            {**result(), "workflow_id": "other"}, {"workflow_id": "new_installation"}
        )


def test_explicit_heading_and_batch_boundaries(monkeypatch, queue, config):
    assert installation_header(" \n 가입자 신규설치 \nSN : 00001")
    assert not installation_header("문의합니다\n" + FORM)
    assert not installation_header("신규설치가 필요한가요?")
    jobs = ImageReplyQueue(queue)
    journal = OperationJournal(queue)
    sms = InstallationSMS(config, journal, queue.event, lambda _: None)
    api = Mock()
    api.run.return_value = parse_unified_result(result("blocked"))
    p = UnifiedProcessor(journal, api, installation_sms=sms)
    monkeypatch.setattr("app.automation.unified_workflow.analyze_request", lambda *a: None)
    job, _ = jobs.enqueue_pair("chat", b"a", b"b")
    msg = incoming("예시입니다.\n" + FORM, FORM)
    for _ in range(2):
        assert p.answer(None, msg, job, threading.Event()) == BLOCKED
    assert api.run.call_count == 1 and api.run.call_args.args[0]["message"] == FORM
    assert (
        p.answer(None, incoming(FORM), "startup", threading.Event(), startup_chat_key="chat")
        is None
    )
    assert api.run.call_count == 1
    # The standalone saved-image processor has no installation notification handler.
    assert (
        UnifiedProcessor(journal, api).answer(None, incoming(FORM), "image", threading.Event())
        is None
    )
    assert api.run.call_count == 1


@pytest.mark.parametrize("scenario", ["overlap", "empty", "changed", "interrupted"])
def test_no_guardian_fallback_or_replay(monkeypatch, queue, config, scenario):
    ImageReplyQueue(queue)
    journal = OperationJournal(queue)
    sms = InstallationSMS(config, journal, queue.event, lambda _: None)
    config.bizgo_installation_test = True
    config.bizgo_test_recipients = {"empty": "", "overlap": "010-0000-2000"}.get(
        scenario, TEST_NUMBERS[0]
    )
    sms.record_routing("job")
    if scenario == "changed":
        config.bizgo_installation_test = False
    factory = Mock(side_effect=Cancelled("stop"))
    monkeypatch.setattr("app.automation.installation_sms.create_bizgo", factory)
    data = asdict(parse_unified_result(result()))
    if scenario == "interrupted":
        with pytest.raises(Cancelled):
            sms.reply(data, "job", "job-0:sms", threading.Event())
    assert "결과를 확인" in sms.reply(data, "job", "job-0:sms", threading.Event())
    assert factory.call_count == int(scenario == "interrupted")


def test_settings_persist_and_validate_test_numbers(config, tmp_path):
    path = tmp_path / "settings.json"
    config.bizgo_installation_test = True
    with pytest.raises(ValueError):
        save(path, config)
    config.bizgo_test_recipients = ", ".join(TEST_NUMBERS)
    save(path, config)
    restored = load(path)
    assert (
        restored.bizgo_installation_test
        and restored.bizgo_test_recipients == config.bizgo_test_recipients
    )


def test_successful_notifications_are_not_repeated_after_restart(config, queue, monkeypatch):
    jobs = ImageReplyQueue(queue)
    job, _ = jobs.enqueue_pair("chat", b"before", b"after")
    api = Mock()
    api.run.return_value = parse_unified_result(result())
    client = Mock()
    client.prepare_installation.return_value = ["guide"]
    client.send.return_value = "accepted"
    config.bizgo_sandbox = False
    monkeypatch.setattr("app.automation.installation_sms.create_bizgo", lambda *a, **kw: client)
    for _ in range(2):
        journal = OperationJournal(queue)
        sms = InstallationSMS(config, journal, queue.event, lambda _: None)
        processor = UnifiedProcessor(journal, api, installation_sms=sms)
        assert processor.answer(None, incoming(FORM), job, threading.Event()) == OK
    assert api.run.call_count == 1 and client.send.call_count == len(GUARDIANS)

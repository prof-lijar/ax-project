import asyncio
import json
import threading
from types import SimpleNamespace

import httpx
import pytest

from app.api.bizgo_client import (
    BIZGO_SAMPLE,
    BizgoClient,
    BizgoSettings,
    create_bizgo,
    phone_number,
    phone_text,
)
from app.automation.monitoring_service import MonitoringService
from app.automation.reply_service import TestReplySender as ReplySender
from app.config import load, save
from app.models import AgentError, Cancelled, State, SubmissionObservation
from tests.test_automation import Capture, Desktop
from tests.test_replies import Composer


def accepted(payload):
    return {
        "common": {"authCode": "A000"},
        "data": {
            "code": "A000",
            "ref": payload["ref"],
            "data": {
                "destinations": [
                    {
                        "to": payload["destinations"][0]["to"],
                        "msgKey": "synthetic-msg-1",
                        "code": "A000",
                    }
                ]
            },
        },
    }


def client(handler, audit=lambda *a: None, sandbox=True):
    return BizgoClient(
        BizgoSettings("01000000001", "01000000002", sandbox, 5),
        "synthetic-api-key",
        audit,
        httpx.MockTransport(handler),
    )


@pytest.mark.parametrize(
    "text,channel", [("x" * 90, "sms"), ("가" * 45, "sms"), ("가" * 46, "mms")]
)
@pytest.mark.parametrize("sandbox", [True, False])
def test_one_send_matches_v2_contract_and_records_acceptance(text, channel, sandbox):
    calls, events = [], []

    def api(request):
        calls.append(request)
        assert (
            str(request.url)
            == ("https://sandbox-mars.ibapi.kr" if sandbox else "https://mars.ibapi.kr")
            + "/api/comm/v1/send/omni"
        )
        assert request.headers["Authorization"] == "synthetic-api-key"  # No Bearer prefix in v2.
        payload = json.loads(request.content)
        assert payload["ref"] == payload["idempotencyKey"] == "capture-id"
        assert payload["idempotencyTtl"] == 86400
        assert payload["destinations"] == [{"to": "01000000002"}]
        assert len(payload["messageFlow"]) == 1
        content = payload["messageFlow"][0][channel]
        assert content["from"] == "01000000001" and content["text"] == text
        assert ("title" in content) == (channel == "mms")
        assert "fileKey" not in content
        return httpx.Response(200, json=accepted(payload))

    sender = client(api, lambda *a: events.append(a), sandbox)
    result = sender.send(sender.prepare(text, "capture-id"), threading.Event())
    assert len(calls) == 1 and [e[0] for e in events] == ["bizgo_attempt", "bizgo_accepted"]
    assert ("no real message delivered" in result) == sandbox
    assert ("final delivery pending" in result) != sandbox
    assert "01000000002" not in str(events) and "synthetic-api-key" not in str(events)


def test_phone_copy_has_explicit_encoding_and_length_handling():
    original = "[test]\n" + "한글 " * 800 + "😀"
    text, warnings = phone_text(original)
    assert len(text.encode("euc-kr")) <= 2000
    assert text.startswith("[test]\n") and text.endswith(
        "[Shortened for LMS; full text in KakaoTalk]"
    )
    assert len(warnings) == 2 and len(original) > len(text)
    assert phone_text("[test] 😀")[0] == "[test] ?"


@pytest.mark.parametrize(
    "failure",
    [
        "401",
        "429",
        "503",
        "redirect",
        "network",
        "auth",
        "service",
        "recipient",
        "mismatch",
        "ref",
        "missing_key",
        "multiple",
        "json",
        "large",
        "duplicate",
    ],
)
def test_failures_never_retry_or_leak_response_text(failure):
    calls, events = [], []
    private = "synthetic-api-key private body 01000000002"

    def api(request):
        calls.append(request)
        if failure.isdigit():
            return httpx.Response(int(failure), text=private)
        if failure == "redirect":
            return httpx.Response(307, headers={"location": "https://other.test"})
        if failure == "network":
            raise httpx.ReadTimeout(private)
        if failure == "json":
            return httpx.Response(200, text=private)
        if failure == "large":
            return httpx.Response(200, content=b"x" * (64 * 1024 + 1))
        body = accepted(json.loads(request.content))
        entry = body["data"]["data"]["destinations"][0]
        if failure == "auth":
            body["common"]["authCode"] = private
        elif failure == "service":
            body["data"]["code"] = "A100"
        elif failure in ("recipient", "duplicate"):
            entry["code"] = "A301" if failure == "duplicate" else "A100"
        elif failure == "mismatch":
            entry["to"] = "01000000009"
        elif failure == "ref":
            body["data"]["ref"] = "other-cycle"
        elif failure == "missing_key":
            del entry["msgKey"]
        elif failure == "multiple":
            body["data"]["data"]["destinations"].append(entry)
        return httpx.Response(200, json=body)

    sender = client(api, lambda *a: events.append(a))
    with pytest.raises(AgentError) as error:
        sender.send(sender.prepare(BIZGO_SAMPLE, "capture-id"), threading.Event())
    assert len(calls) == 1
    for sensitive in ("synthetic-api-key", "private body", "01000000002"):
        assert sensitive not in str(error.value) + str(events)
    assert not any(e[0] == "bizgo_accepted" for e in events)


def test_cancel_before_request_and_audit_failure_send_nothing():
    calls = []
    sender = client(lambda r: calls.append(r))
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled, match="before Bizgo"):
        sender.send(sender.prepare(BIZGO_SAMPLE, "capture-id"), cancel)
    cancel.clear()

    def failed_audit(*a):
        raise OSError("storage unavailable")

    sender.audit = failed_audit
    with pytest.raises(OSError):
        sender.send(sender.prepare(BIZGO_SAMPLE, "capture-id"), cancel)
    assert not calls


def test_cancel_during_post_reports_uncertainty_and_closes_request():
    async def exercise():
        cancel = threading.Event()
        closed = []

        async def api(request):
            try:
                cancel.set()
                await asyncio.sleep(30)
            finally:
                closed.append(True)

        sender = client(api)
        with pytest.raises(Cancelled, match="may already be accepted"):
            await asyncio.wait_for(
                sender.send_async(sender.prepare(BIZGO_SAMPLE, "cycle"), cancel), 1
            )
        assert closed == [True]

    asyncio.run(exercise())


@pytest.mark.parametrize("outcome", ["clear", "uncertain", "cancel_after_kakao", "bizgo_error"])
def test_final_workflow_stage_follows_kakao_once(config, queue, frame, region, outcome):
    desktop = Desktop(region)
    desktop.activate_target = lambda cancel=None: desktop.validate()
    service = MonitoringService(
        desktop,
        Capture(desktop, frame),
        queue,
        config,
        lambda *a: None,
        lambda *a: None,
        lambda *a: None,
    )
    composer = Composer()

    def observe(*a):
        if outcome == "cancel_after_kakao":
            service.stop_input.set()
        return SubmissionObservation("Kakao observation", outcome != "uncertain")

    composer.observe_submission = observe
    service.test_workflow.sender = ReplySender(composer, queue.event, service.stop_input)
    service.test_workflow.llm_factory = lambda _: SimpleNamespace(
        run=lambda *a: "[test]\n-- Done: simulated\n-- Request: hello"
    )
    calls = []

    def api(request):
        assert composer.submits == [10]  # Bizgo follows the Kakao submission.
        calls.append(request)
        if outcome == "bizgo_error":
            return httpx.Response(401)
        return httpx.Response(200, json=accepted(json.loads(request.content)))

    service.test_workflow.bizgo_factory = lambda config, audit: client(api, audit)
    if outcome in ("cancel_after_kakao", "bizgo_error"):
        with pytest.raises(AgentError) as error:
            service.dispatch("test_workflow")
        if outcome == "bizgo_error":
            assert "KakaoTalk reply already requested" in str(error.value)
    else:
        service.dispatch("test_workflow")
        assert service.state == State.STOPPED
        assert ("Bizgo skipped" in service.reason) == (outcome == "uncertain")
    assert len(calls) == (1 if outcome in ("clear", "bizgo_error") else 0)
    assert composer.submits == [10] and service.stop_input.is_set()


def test_missing_bizgo_setup_fails_before_capture_or_kakao(config, queue, frame, region):
    desktop = Desktop(region)  # No activate_target: reaching capture would fail this test.
    service = MonitoringService(
        desktop,
        Capture(desktop, frame),
        queue,
        config,
        lambda *a: None,
        lambda *a: None,
        lambda *a: None,
    )
    service.test_workflow.llm_factory = lambda _: None
    config.bizgo_enabled = True
    with pytest.raises(AgentError, match="8–15 digits"):
        service.dispatch("test_workflow")
    assert not list(queue.images.glob("*.png"))


def test_bizgo_settings_persist_and_disabled_defaults_need_no_secrets(config, tmp_path):
    assert not config.bizgo_enabled and config.bizgo_sandbox
    assert create_bizgo(config, lambda *a: None) is None
    config.bizgo_enabled = True
    config.bizgo_sender = "010-0000-0001"
    config.bizgo_recipient = "010 0000 0002"
    save(tmp_path / "config.json", config)
    restored = load(tmp_path / "config.json")
    settings = BizgoSettings.resolve(restored)
    assert settings.sender == "01000000001" and settings.recipient == "01000000002"
    assert settings.sandbox
    for invalid in ("", "123", "01000000002,01000000003", "https://example.test"):
        with pytest.raises(ValueError):
            phone_number(invalid)


def test_standalone_sample_needs_no_chat_capture_or_llm(config, queue, frame, region, monkeypatch):
    from app.automation import monitoring_service

    desktop = Desktop(region)
    desktop.valid = False
    service = MonitoringService(
        desktop,
        Capture(desktop, frame),
        queue,
        config,
        lambda *a: None,
        lambda *a: None,
        lambda *a: None,
    )
    calls = []

    def api(request):
        payload = json.loads(request.content)
        calls.append(payload)
        assert payload["messageFlow"][0]["sms"]["text"] == BIZGO_SAMPLE
        return httpx.Response(200, json=accepted(payload))

    monkeypatch.setattr(monitoring_service, "create_bizgo", lambda *a, **kw: client(api))
    service.dispatch("bizgo_test")
    assert len(calls) == 1 and service.state == State.STOPPED
    assert not list(queue.images.glob("*.png"))

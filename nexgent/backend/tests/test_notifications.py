import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import os
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.engine import make_url

from conftest import authenticated_headers, feature_app
from app.identity.models import now
from app.identity.store import AccessError
from app.notifications.config import NotificationSettings, load_notification_settings
from app.notifications.persistence import Notification, RateGate
from app.notifications.schemas import SlackNotification
from app.notifications.service import NotificationService
from app.notifications.slack import DeliveryError, SlackClient, render_message, retry_after
from app.notifications.store import NotificationStore
from app.notifications.worker import execute


@pytest.fixture
def settings():
    return NotificationSettings(enabled=True, bot_token="xoxb-test-secret",
                                service_token="test-service-secret-" * 3,
                                channels={"default": "C0123456789", "alerts": "C9876543210"})


@pytest.fixture
def store(tmp_path, monkeypatch):
    maintenance = os.getenv("NEXGENT_TEST_DATABASE_URL")
    admin = None
    if maintenance:
        name = "notifications_test_" + uuid4().hex
        admin = create_engine(maintenance, isolation_level="AUTOCOMMIT")
        with admin.connect() as db:
            db.exec_driver_sql(f'CREATE DATABASE "{name}"')
        url = make_url(maintenance).set(database=name).render_as_string(hide_password=False)
    else:
        url = f"sqlite:///{tmp_path / 'notifications.db'}"
    monkeypatch.setenv("NEXGENT_DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(url)
    if engine.dialect.name == "sqlite":
        engine = engine.execution_options(schema_translate_map={"notifications": None})
    result = NotificationStore(engine, "test")
    result.ready()
    try:
        yield result
    finally:
        engine.dispose()
        if admin:
            with admin.connect() as db:
                db.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
            admin.dispose()


@pytest.fixture
def api(store, settings):
    app = feature_app()
    app.state.identity_store.engine = store.engine
    app.state.notification_settings = settings.model_copy(update={"deployment": "test"})
    client = TestClient(app)
    yield client
    client.close()


def submit(store, settings, key="one", owner="user:alice", **kwargs):
    return NotificationService(store, settings).submit(owner, SlackNotification(text="Report ready", **kwargs), key)


def make_due(store):
    with store.sessions.begin() as db:
        stamp = now() - timedelta(seconds=1)
        db.execute(update(RateGate).values(available_at=stamp))
        db.execute(update(Notification).values(available_at=stamp, lease_until=stamp))


def test_config_optional_and_secrets_redacted(monkeypatch, settings):
    for name in list(os.environ):
        if name.startswith(("NEXGENT_SLACK_", "NEXGENT_NOTIFICATION_")):
            monkeypatch.delenv(name)
    assert not load_notification_settings().enabled
    assert "xoxb-test-secret" not in repr(settings)
    monkeypatch.setenv("NEXGENT_SLACK_ENABLED", "true")
    with pytest.raises(RuntimeError, match="Invalid notification configuration"):
        load_notification_settings()
    monkeypatch.setenv("NEXGENT_SLACK_CHANNELS", '{"default":"https://secret.invalid"}')
    with pytest.raises(RuntimeError) as exc:
        load_notification_settings()
    assert "secret.invalid" not in str(exc.value)


def test_api_submission_polling_and_idempotency(api):
    headers = {**authenticated_headers(), "Idempotency-Key": "report:42"}
    first = api.post("/api/notifications/slack", headers=headers, json={"text": "Done"})
    assert first.status_code == 202, first.text
    assert first.json()["status"] == "queued"
    assert "text" not in first.json() and "channel_id" not in first.json()
    again = api.post("/api/notifications/slack", headers=headers, json={"text": "Done"})
    assert again.json()["id"] == first.json()["id"]
    conflict = api.post("/api/notifications/slack", headers=headers, json={"text": "Different"})
    assert conflict.status_code == 409
    assert api.get(first.headers["Location"], headers=authenticated_headers()).json() == first.json()
    caps = api.get("/api/notifications/capabilities", headers=authenticated_headers()).json()
    assert caps == {"enabled": True, "destinations": ["alerts", "default"]}


def test_browser_and_agent_auth_are_scoped(api, settings):
    path = "/api/notifications/slack"
    payload = {"text": "Done"}
    key = {"Idempotency-Key": "one"}
    assert api.post(path, headers=key, json=payload).status_code == 401
    cookie_only = {**key, "Cookie": authenticated_headers()["Cookie"]}
    assert api.post(path, headers=cookie_only, json=payload).status_code == 403
    bad_csrf = {**authenticated_headers(), **key, "X-CSRF-Token": "wrong"}
    assert api.post(path, headers=bad_csrf, json=payload).status_code == 403
    agent = {**key, "Authorization": "Bearer " + settings.service_token.get_secret_value()}
    sent = api.post(path, headers=agent, json=payload)
    assert sent.status_code == 202
    assert api.get(sent.headers["Location"], headers=agent).status_code == 200
    assert api.get(sent.headers["Location"], headers=authenticated_headers()).status_code == 404
    assert api.get("/api/me", headers=agent).status_code == 401
    assert api.get("/api/nextcloud/files", headers=agent).status_code == 401
    assert api.post(path, headers={**key, "Authorization": "Bearer wrong"}, json=payload).status_code == 401
    api.app.state.notification_settings = settings.model_copy(update={"service_token": type(settings.service_token)("")})
    assert api.post(path, headers=agent, json=payload).status_code == 401


@pytest.mark.parametrize("payload", [
    {"text": " "}, {"text": "x" * 4001}, {"text": "Hi", "channel": "C0123456789"},
    {"text": "Hi", "destination": "missing"}, {"text": "Hi", "url": "javascript:alert(1)"},
    {"text": "Hi", "url": "https://user:secret@example.org"},
    {"text": "Hi", "fields": [{"name": "x", "value": "y"}] * 11},
    {"text": "Hi", "thread_ts": "invalid"}, {"text": "Hi", "blocks": []},
])
def test_invalid_payload_never_enqueues(api, store, payload):
    response = api.post("/api/notifications/slack", json=payload,
                        headers={**authenticated_headers(), "Idempotency-Key": "invalid"})
    assert response.status_code == 422
    with store.sessions() as db:
        assert db.scalar(select(Notification.id)) is None


def test_idempotency_key_required_and_disabled_behavior(api, settings):
    path = "/api/notifications/slack"
    assert api.post(path, json={"text": "Hi"}, headers=authenticated_headers()).status_code == 422
    api.app.state.notification_settings = settings.model_copy(update={"enabled": False})
    response = api.post(path, json={"text": "Hi"}, headers={**authenticated_headers(), "Idempotency-Key": "one"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "notifications_disabled"


def test_ownership_deployment_and_config_change(store, settings):
    first = submit(store, settings)
    with pytest.raises(AccessError) as exc:
        store.get("user:bob", first["id"])
    assert exc.value.status == 404
    other = NotificationStore(store.engine, "other-deployment")
    with pytest.raises(AccessError):
        other.get("user:alice", first["id"])
    assert submit(other, settings)["id"] != first["id"]
    remapped = settings.model_copy(update={"channels": {"default": "C1111111111"}})
    assert submit(store, remapped)["id"] == first["id"]
    job = store.claim(settings)
    class NeverSend:
        async def send(self, job):
            pytest.fail("A revoked destination must not receive queued payloads")
    asyncio.run(execute(store, NeverSend(), job, remapped))
    assert store.get("user:alice", first["id"])["error_code"] == "notification_destination_changed"


def test_shared_channel_gate_and_lease_recovery(store, settings):
    submit(store, settings)
    submit(store, settings, key="two")
    submit(store, settings, key="three", destination="alerts")
    job = store.claim(settings)
    other = store.claim(settings)
    assert {job["channel_id"], other["channel_id"]} == set(settings.channels.values())
    assert store.claim(settings) is None
    make_due(store)
    # Make the expired first job the oldest candidate deterministically.
    with store.sessions.begin() as db:
        db.execute(update(Notification).where(Notification.id == job["id"]).values(available_at=now() - timedelta(days=1)))
    recovered = store.claim(settings)
    assert recovered["id"] == job["id"] and recovered["token"] != job["token"]
    assert recovered["attempts"] == 2
    assert not store.finish(job, slack_ts="1234567890.123456")
    assert store.finish(recovered, slack_ts="1234567890.123456")
    assert store.get("user:alice", recovered["id"])["status"] == "sent"


def test_idempotency_handles_concurrent_submissions(store, settings):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: submit(store, settings), range(16)))
    assert len({result["id"] for result in results}) == 1


def test_postgres_concurrent_workers_claim_distinct_jobs(store, settings):
    if store.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL is required to exercise row locks")
    for i in range(12):
        store.enqueue("service:test", str(i), str(i), "default", f"C{i:010}", {"text": "Hi"})
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: store.claim(settings), range(48)))
    jobs = [job for job in results if job]
    # SKIP LOCKED may return no job while another claim holds the workspace
    # gate. Future polls drain the remaining work without claiming any twice.
    while job := store.claim(settings):
        jobs.append(job)
    assert len(jobs) == 12
    assert len({job["id"] for job in jobs}) == 12


def test_postgres_concurrent_claims_respect_same_channel_gate(store, settings):
    if store.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL is required to exercise row locks")
    for i in range(8):
        submit(store, settings, key=str(i))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: store.claim(settings), range(24)))
    assert len([job for job in results if job]) == 1


def test_rendering_is_bounded_and_mentions_are_literal():
    body = SlackNotification(text="<!channel> " + "한" * 3900, title="Complete", severity="success",
                             fields=[{"name": "Count", "value": "12"}], url="https://example.org/report",
                             thread_ts="1234567890.123456")
    result = render_message({"id": str(uuid4()), "channel_id": "C0123456789", "payload": body.model_dump(mode="json")})
    assert result["thread_ts"] == "1234567890.123456"
    assert result["parse"] == "none" and result["mrkdwn"] is False
    assert "<!channel>" not in result["text"]
    assert "Count: 12" in result["text"]
    for block in result["blocks"]:
        if block["type"] == "section" and "text" in block:
            assert block["text"]["type"] == "plain_text" and len(block["text"]["text"]) <= 3000


def test_delivery_success_persists_slack_reference(store, settings):
    submitted = submit(store, settings, title="Report")
    job = store.claim(settings)
    def handler(request):
        assert str(request.url) == "https://slack.com/api/chat.postMessage"
        assert request.headers["authorization"] == "Bearer xoxb-test-secret"
        assert json.loads(request.content)["client_msg_id"] == submitted["id"]
        return httpx.Response(200, json={"ok": True, "ts": "1234567890.123456"})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await execute(store, SlackClient(client, settings), job, settings)
    asyncio.run(run())
    result = store.get("user:alice", submitted["id"])
    assert result["status"] == "sent" and result["sent_at"]
    assert result["slack_ts"] == "1234567890.123456" and result["attempts"] == 1


@pytest.mark.parametrize("status,body,code,retryable", [
    (200, {"ok": False, "error": "invalid_auth"}, "slack_authentication_failed", False),
    (200, {"ok": False, "error": "not_in_channel"}, "slack_destination_unavailable", False),
    (200, {"ok": False, "error": "internal_error"}, "slack_unavailable", True),
    (200, {"ok": False, "error": "secret upstream text"}, "slack_rejected", False),
    (200, {"ok": True}, "slack_invalid_response", True),
    (200, [], "slack_invalid_response", True),
    (503, {}, "slack_unavailable", True),
    (302, {}, "slack_http_error", False),
])
def test_provider_errors_are_classified_and_sanitized(settings, status, body, code, retryable):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(status, json=body))) as client:
            with pytest.raises(DeliveryError) as exc:
                await SlackClient(client, settings).send({"id": str(uuid4()), "channel_id": "C0123456789",
                    "payload": SlackNotification(text="Hi").model_dump(mode="json")})
            assert exc.value.code == code and exc.value.retryable == retryable
    asyncio.run(run())


@pytest.mark.parametrize("attempts", [1, 5])
def test_rate_limit_cools_entire_workspace_including_exhaustion(store, settings, attempts):
    settings = settings.model_copy(update={"max_attempts": attempts})
    first = submit(store, settings)
    job = store.claim(settings)
    submit(store, settings, key="two", destination="alerts")
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(429, headers={"Retry-After": "120"}),
        )) as client:
            await execute(store, SlackClient(client, settings), job, settings)
    asyncio.run(run())
    result = store.get("user:alice", first["id"])
    assert result["status"] == ("failed" if attempts == 1 else "queued")
    assert result["error_code"] == "slack_rate_limited"
    assert store.claim(settings) is None
    with store.sessions() as db:
        assert db.scalar(select(RateGate).where(RateGate.key == "workspace", RateGate.available_at > now() + timedelta(seconds=110)))


def test_transport_retry_and_attempt_exhaustion(store, settings):
    settings = settings.model_copy(update={"max_attempts": 2})
    result = submit(store, settings)
    class TimeoutSender:
        async def send(self, job):
            raise DeliveryError("slack_transport_error", retryable=True)
    for expected in ("queued", "failed"):
        asyncio.run(execute(store, TimeoutSender(), store.claim(settings), settings))
        assert store.get("user:alice", result["id"])["status"] == expected
        make_due(store)
    assert store.claim(settings) is None


def test_crash_recovery_has_attempt_limit(store, settings):
    settings = settings.model_copy(update={"max_attempts": 1})
    result = submit(store, settings)
    assert store.claim(settings)
    make_due(store)
    assert store.claim(settings) is None
    assert store.get("user:alice", result["id"])["status"] == "failed"


@pytest.mark.parametrize("header,expected", [("120", 120), ("garbage", 60), ("NaN", 60), ("-2", 60), ("inf", 60)])
def test_retry_after_validation(header, expected):
    assert retry_after(httpx.Response(429, headers={"Retry-After": header})) == expected


@pytest.mark.parametrize("failure", ["timeout", "connection", "malformed"])
def test_transport_and_malformed_responses_are_retryable(settings, failure):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("sensitive upstream text", request=request)
        if failure == "connection":
            raise httpx.ConnectError("sensitive upstream text", request=request)
        return httpx.Response(200, content=b"not JSON sensitive upstream text")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(DeliveryError) as exc:
                await SlackClient(client, settings).send({"id": str(uuid4()), "channel_id": "C0123456789",
                    "payload": SlackNotification(text="Hi").model_dump(mode="json")})
            assert exc.value.retryable
            assert "sensitive" not in str(exc.value)
    asyncio.run(run())

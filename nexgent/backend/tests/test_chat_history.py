import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from app.chat.config import get_chat_settings
from app.chat.persistence import Run
from app.chat.store import ChatStore
from app.chat.vault import FileVault
from app.chat.worker import execute
from app.identity.config import IdentitySettings
from app.identity.models import ADMIN_ROLE_ID, now
from app.identity.store import AccessError, IdentityStore
from app.main import create_app


@pytest.fixture
def chat(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_CHAT_FILE_ROOT", str(tmp_path / "files"))
    monkeypatch.setenv("AX_CHAT_ARTIFACT_ROOT", str(tmp_path / "staging"))
    monkeypatch.setenv("AX_CHAT_DEPLOYMENT", "test")
    maintenance = os.getenv("NEXGENT_TEST_DATABASE_URL")
    admin_engine = None
    if maintenance:
        name = "chat_test_" + uuid4().hex
        admin_engine = create_engine(maintenance, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as db:
            db.exec_driver_sql(f'CREATE DATABASE "{name}"')
        url = (
            make_url(maintenance)
            .set(database=name)
            .render_as_string(hide_password=False)
        )
    else:
        url = f"sqlite:///{tmp_path / 'chat.db'}"
    monkeypatch.setenv("NEXGENT_DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(url)
    if engine.dialect.name == "sqlite":
        engine = engine.execution_options(
            schema_translate_map={"auth": None, "chat": None, "file_storage": None}
        )

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    settings = IdentitySettings(url, "https://chat.test", "x" * 48)
    identity = IdentityStore(settings, engine)
    users = [
        identity.create_user(
            None,
            username=name,
            name=name,
            email="",
            password="test-pass",
            role_ids=[ADMIN_ROLE_ID] if name == "alice" else [],
            group_ids=[],
        )
        for name in ("alice", "bob")
    ]
    app = create_app(identity_settings=settings, identity_store=identity)
    app.state.chat_store = store = ChatStore(engine)
    try:
        with TestClient(app, base_url=settings.public_url) as client:

            def login(name="alice"):
                assert (
                    client.post(
                        "/auth/login",
                        json={"username": name, "password": "test-pass"},
                        headers={"Origin": settings.public_url},
                    ).status_code
                    == 200
                )
                return {
                    "Origin": settings.public_url,
                    "X-CSRF-Token": client.get("/api/me").json()["csrf_token"],
                }

            yield client, store, users, login, FileVault(get_chat_settings())
    finally:
        engine.dispose()
        if admin_engine:
            with admin_engine.connect() as db:
                db.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
            admin_engine.dispose()


def submit(
    chat,
    *,
    conversation=None,
    prompt="Remember my name is Alice",
    files=None,
    selected=None,
    key=None,
):
    client, _, _, login, _ = chat
    headers = {**login(), "Idempotency-Key": key or str(uuid4())}
    path = (
        f"/api/chat/conversations/{conversation}/messages"
        if conversation
        else "/api/chat/conversations"
    )
    return client.post(
        path,
        headers=headers,
        data={"prompt": prompt, "attachment_ids": selected or []},
        files=files,
    )


def complete(chat, text="Hello Alice"):
    store = chat[1]
    job = store.claim()
    assert job
    assert store.output(job["id"], job["token"], text, "completed")
    return job


def test_reload_resume_titles_pagination_and_full_transcript(chat):
    client, store, users, login, _ = chat
    result = submit(chat).json()
    complete(chat)
    ident = result["conversation_id"]
    # A fresh store instance uses only persisted data; reading does not reorder activity.
    restored = ChatStore(store.engine)
    before = restored.conversation(users[0]["id"], ident)
    assert (
        client.patch(
            f"/api/chat/conversations/{ident}",
            json={"title": " My work "},
            headers=login(),
        ).status_code
        == 200
    )
    assert restored.conversation(users[0]["id"], ident)["title"] == "My work"
    assert (
        restored.conversation(users[0]["id"], ident)["updated_at"]
        == before["updated_at"]
    )
    reply = submit(chat, conversation=ident, prompt="What is my name?").json()
    assert restored.input(reply["run_id"])[1] == [
        {"user": "Remember my name is Alice", "assistant": "Hello Alice"}
    ]
    complete(chat, "Alice")
    page = client.get(f"/api/chat/conversations/{ident}/messages?limit=2").json()
    assert [m["content"] for m in page["items"]] == ["What is my name?", "Alice"]
    older = client.get(
        f"/api/chat/conversations/{ident}/messages",
        params={"cursor": page["next_cursor"]},
    ).json()
    assert [m["content"] for m in older["items"]] == [
        "Remember my name is Alice",
        "Hello Alice",
    ]
    assert (
        client.get(f"/api/chat/runs/{reply['run_id']}/events").text.count(
            "event: snapshot"
        )
        == 1
    )


def test_all_resources_are_private_including_admin_and_legacy_route(chat):
    client, _, _, login, _ = chat
    result = submit(
        chat, files={"files": ("memo.txt", b"private", "text/plain")}
    ).json()
    ident, run = result["conversation_id"], result["run_id"]
    file_id = client.get(f"/api/chat/conversations/{ident}/attachments").json()[
        "items"
    ][0]["id"]
    headers = login("bob")
    assert client.get("/api/chat/conversations").json()["items"] == []
    for path in (
        f"conversations/{ident}",
        f"conversations/{ident}/messages",
        f"conversations/{ident}/attachments",
        f"runs/{run}",
        f"runs/{run}/events",
        f"attachments/{file_id}/download",
    ):
        assert client.get("/api/chat/" + path).status_code == 404
    assert (
        client.patch(
            f"/api/chat/conversations/{ident}",
            headers=headers,
            json={"title": "stolen"},
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/chat/conversations/{ident}", headers=headers).status_code
        == 404
    )
    assert (
        client.post(f"/api/chat/runs/{run}/cancel", headers=headers).status_code == 404
    )
    assert (
        client.post(
            "/api/chat/stream",
            headers=headers,
            data={"prompt": "steal", "session_id": ident},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/chat/conversations/{ident}/messages",
            headers={**headers, "Idempotency-Key": "steal"},
            data={"prompt": "steal"},
        ).status_code
        == 404
    )
    # Admin does not get another account's chats either.
    bob = client.post(
        "/api/chat/conversations",
        headers={**headers, "Idempotency-Key": "bob"},
        data={"prompt": "bob private"},
    ).json()
    login("alice")
    assert (
        client.get(f"/api/chat/conversations/{bob['conversation_id']}").status_code
        == 404
    )


def test_idempotency_busy_and_deployment_isolation(chat):
    client, store, users, _, _ = chat
    first = submit(chat, key="same").json()
    assert submit(chat, key="same").json() == first
    assert submit(chat, key="same", prompt="changed").status_code == 409
    assert submit(chat, conversation=first["conversation_id"]).status_code == 409
    other = ChatStore(store.engine, "other")
    assert other.conversations(users[0]["id"])["items"] == []
    assert other.claim() is None
    with pytest.raises(AccessError):
        other.conversation(users[0]["id"], first["conversation_id"])
    complete(chat)
    assert submit(chat, key="same").json() == first
    assert (
        len(
            client.get(
                f"/api/chat/conversations/{first['conversation_id']}/messages"
            ).json()["items"]
        )
        == 2
    )


def test_files_original_download_reuse_and_delete(chat):
    client, store, _users, login, vault = chat
    content = b"original\r\nfile"
    result = submit(chat, files={"files": ("notes.txt", content, "text/plain")}).json()
    ident = result["conversation_id"]
    complete(chat)
    file = client.get(f"/api/chat/conversations/{ident}/attachments").json()["items"][0]
    response = client.get(f"/api/chat/attachments/{file['id']}/download")
    assert response.content == content
    assert "attachment;" in response.headers["content-disposition"]
    followup = submit(chat, conversation=ident, selected=[file["id"]]).json()
    _prompt, history, files = store.input(followup["run_id"])
    assert files[0]["id"] == file["id"] and history
    staged = vault.stage(files)
    assert (
        Path(staged.attachments[0].uri.removeprefix("file://")).read_bytes()
        == b"original\nfile"
    )
    asyncio.run(staged.cleanup())
    assert vault.read(files[0]) == content
    # Reuse cannot cross conversations, even for the same owner.
    other = submit(chat).json()["conversation_id"]
    assert submit(chat, conversation=other, selected=[file["id"]]).status_code == 404
    assert (
        client.delete(f"/api/chat/conversations/{ident}", headers=login()).status_code
        == 204
    )
    assert client.get(f"/api/chat/attachments/{file['id']}/download").status_code == 404
    for deleted, ids in store.garbage():
        for item in ids:
            vault.remove(item)
        store.purge(deleted)
    assert not vault.directory(file["id"]).exists()


def test_cancel_expired_leases_partial_output_and_late_writes(chat):
    client, store, users, login, _ = chat
    first = submit(chat).json()
    job = store.claim()
    store.output(job["id"], job["token"], "partial")
    assert (
        client.post(f"/api/chat/runs/{job['id']}/cancel", headers=login()).status_code
        == 202
    )
    assert not store.heartbeat(job["id"], job["token"])
    assert not store.output(job["id"], job["token"], "partial tail", "completed")
    snapshot = store.run(users[0]["id"], job["id"])
    assert (
        snapshot["status"] == "stopped"
        and snapshot["message"]["content"] == "partial tail"
    )
    second = submit(chat, conversation=first["conversation_id"]).json()
    job = store.claim()
    store.output(job["id"], job["token"], "before crash")
    with store.sessions.begin() as db:
        db.get(Run, job["id"]).lease_until = now() - timedelta(seconds=1)
    assert not store.heartbeat(job["id"], job["token"])
    assert not store.output(job["id"], job["token"], "late completion", "completed")
    store.recover()
    assert store.run(users[0]["id"], second["run_id"])["status"] == "interrupted"
    assert (
        store.input(second["run_id"])[1] == []
    )  # Failed/partial pairs never become context.


def test_deleted_running_chat_cannot_be_resurrected(chat):
    _, store, users, _, _ = chat
    result = submit(chat).json()
    job = store.claim()
    store.remove(users[0]["id"], result["conversation_id"])
    assert not store.garbage()
    assert not store.output(job["id"], job["token"], "late", "completed")
    assert store.garbage()
    with pytest.raises(AccessError):
        store.run(users[0]["id"], job["id"])


class FakeResponse:
    def __init__(self, frames):
        self.frames = frames

    async def aiter_lines(self):
        for frame in self.frames:
            for line in frame.splitlines():
                yield line


class FakeUpstream:
    def __init__(self, frames):
        self.response = FakeResponse(frames)
        self.closed = False

    async def close(self):
        self.closed = True


@pytest.mark.parametrize("complete_event", [True, False])
def test_worker_saves_without_browser_and_requires_completion(
    chat, monkeypatch, complete_event
):
    from app.chat import worker

    _, store, users, _, vault = chat
    result = submit(
        chat, files={"files": ("memo.txt", b"remember", "text/plain")}
    ).json()
    frames = ['event: custom\ndata: {"response_delta":"Hello"}\n\n']
    if complete_event:
        frames.append('event: custom\ndata: {"response_complete":"Hello"}\n\n')
    upstream = FakeUpstream(frames)

    async def open_stream(prompt, attachments, settings, **kwargs):
        assert kwargs["history"] == [] and len(attachments) == 1
        return upstream

    monkeypatch.setattr(worker, "open_agent_stream", open_stream)
    # Submission completed before the worker starts; there is no browser stream.
    asyncio.run(execute(store, vault, store.claim(), get_chat_settings()))
    snapshot = store.run(users[0]["id"], result["run_id"])
    assert snapshot["status"] == ("completed" if complete_event else "failed")
    assert snapshot["message"]["content"] == "Hello"
    assert upstream.closed and not list(vault.settings.artifact_root.iterdir())
    assert len(list(vault.root.iterdir())) == 1


def test_parallel_submission_is_one_run_on_postgres(chat):
    _, store, users, _, _ = chat
    if store.engine.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    barrier = Barrier(2)

    def send():
        barrier.wait()
        return store.submit(users[0]["id"], None, "hello", "parallel", [], [])[0]

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: send(), range(2)))
    assert results[0] == results[1]
    assert len(store.conversations(users[0]["id"])["items"]) == 1


def test_retried_upload_does_not_duplicate_files(chat):
    payload = {"files": ("memo.txt", b"same bytes", "text/plain")}
    first = submit(chat, key="file-retry", files=payload)
    second = submit(chat, key="file-retry", files=payload)
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert len(list(chat[4].root.iterdir())) == 1


def test_storage_failure_does_not_acknowledge_or_keep_unlinked_files(chat, monkeypatch):
    def unavailable(*args):
        raise OperationalError("test", {}, RuntimeError("test outage"))

    monkeypatch.setattr(chat[1], "submit", unavailable)
    response = submit(
        chat, files={"files": ("memo.txt", b"not committed", "text/plain")}
    )
    assert response.status_code == 503
    assert not list(chat[4].root.iterdir())


def test_authentication_csrf_and_invalid_cursors(chat):
    client, _, _, login, _ = chat
    assert client.get("/api/chat/conversations").status_code == 401
    assert (
        client.post(
            "/api/chat/conversations", data={"prompt": "unauthorized"}
        ).status_code
        == 401
    )
    login()
    assert (
        client.post(
            "/api/chat/conversations", data={"prompt": "missing csrf"}
        ).status_code
        == 403
    )
    assert client.get("/api/chat/conversations?cursor=not-valid").status_code == 422

import json
import os
import time
from dataclasses import replace

import pytest

from app.capture.screen_capture import encode_png
from app.config import Config
from app.models import AgentError, Target
from app.storage.capture_queue import CaptureQueue
from app.storage.chat_paths import chat_directory, chat_folder_name
from app.storage.image_reply_queue import CaptureReviewRequired, ImageReplyQueue


def chat(title="서울 돌봄팀", chat_id="seoul", hwnd=1):
    return Config(
        chat_id=chat_id,
        target=Target(hwnd, 1, "start", "KakaoTalk.exe", "chat", title),
    )


@pytest.mark.parametrize(
    "title",
    [
        "서울 돌봄팀",
        'East / West: <care>?*|"\\',
        "CON",
        "NUL.txt",
        "...  ",
        "A\nB\x00C",
        "😀" * 120,
    ],
)
def test_group_folder_names_are_readable_and_windows_safe(tmp_path, title):
    config = chat(title)
    folder = chat_folder_name(config)
    assert folder and not set('<>:"/\\|?*\x00\n').intersection(folder)
    assert not folder.startswith((".", " "))
    assert len(folder.encode("utf-16-le")) <= 150
    assert chat_directory(tmp_path, folder).parent == tmp_path
    assert chat_folder_name(config) == folder
    if title == "서울 돌봄팀":
        assert folder.startswith("서울 돌봄팀--")


def test_same_named_groups_and_recreated_windows_keep_correct_folders():
    first = chat()
    second = chat(chat_id="different-chat", hwnd=2)
    assert chat_folder_name(first) != chat_folder_name(second)
    recreated = replace(first, target=replace(first.target, hwnd=100, pid=200))
    assert chat_folder_name(recreated) == chat_folder_name(first)


def test_identical_images_are_physically_separate_and_queued_per_chat(queue, frame):
    jobs = ImageReplyQueue(queue)
    png = encode_png(frame)
    folders = [chat_folder_name(chat(chat_id=f"chat-{i}", hwnd=i)) for i in (1, 2, 3)]
    ids, paths = [], []
    for index, folder in enumerate(folders):
        job_id, path = jobs.enqueue_pair(str(index), png, png, folder=folder)
        ids.append(job_id)
        paths.append(path)
    assert len(set(paths)) == 3 and len({p.name for p in paths}) == 1
    for index, path in enumerate(paths):
        assert path.parent == jobs.images / folders[index]
        assert path.read_bytes() == png
        job = jobs.claim(str(index))
        assert job["job_id"] == ids[index] and jobs.load_images(job) == [png, png]
    # Restart restores pending work using its stored directory, not active settings.
    queue.config.target = chat("Different selected room").target
    restarted = ImageReplyQueue(queue)
    for index in range(3):
        job = restarted.claim(str(index))
        assert job["job_id"] == ids[index]
        assert restarted.load_images(job) == [png, png]


@pytest.mark.parametrize("status", ["pending", "sent", "review"])
def test_old_flat_startup_capture_is_not_duplicated_on_upgrade(queue, frame, status):
    jobs = ImageReplyQueue(queue)
    png = encode_png(frame)
    original_id, original_path = jobs.enqueue_pair("chat", png, png, mode="latest")
    jobs.finish(original_id, status)
    result = jobs.enqueue_pair("chat", png, png, mode="latest", folder=chat_folder_name(chat()))
    assert result == (original_id, original_path)
    with queue.connect() as db:
        rows = db.execute("SELECT * FROM image_reply_queue").fetchall()
    assert len(rows) == 1 and rows[0]["status"] == status
    assert jobs.load_images(rows[0]) == [png, png]


@pytest.mark.parametrize(
    "folder", ["../escape", "/tmp/escape", "C:\\escape", "..", "bad/name--123456789abc"]
)
def test_queued_folder_paths_cannot_escape_capture_root(queue, frame, folder):
    jobs = ImageReplyQueue(queue)
    png = encode_png(frame)
    with pytest.raises(AgentError, match="folder"):
        jobs.enqueue_pair("chat", png, png, folder=folder)
    job_id, _ = jobs.enqueue_pair("chat", png, png)
    with queue.connect() as db:
        row = db.execute("SELECT text FROM image_reply_queue WHERE job_id=?", (job_id,)).fetchone()
        body = dict(json.loads(row["text"]), folder=folder)
        db.execute("UPDATE image_reply_queue SET text=? WHERE job_id=?", (json.dumps(body), job_id))
    job = jobs.claim("chat")
    with pytest.raises(CaptureReviewRequired):
        jobs.load_images(job)
    assert jobs.review_count("chat") == 1


def test_retention_in_one_group_preserves_identical_images_in_another(queue, frame):
    jobs = ImageReplyQueue(queue)
    png = encode_png(frame)
    first, first_path = jobs.enqueue_pair("a", png, png, folder=chat_folder_name(chat("A")))
    second, second_path = jobs.enqueue_pair("b", png, png, folder=chat_folder_name(chat("B")))
    jobs.finish(first, "sent")
    old = time.time() - (queue.config.metadata_retention_days + 1) * 86400
    with queue.connect() as db:
        db.execute("UPDATE image_reply_queue SET created_at=?", (old,))
    for path in (first_path, second_path):
        os.utime(path, (old, old))
        path.with_suffix(".tmp").write_bytes(b"partial")
    restarted = ImageReplyQueue(queue)
    assert not first_path.exists() and second_path.exists()
    assert not list(jobs.images.rglob("*.tmp"))
    job = restarted.claim("b")
    assert job["job_id"] == second and restarted.load_images(job) == [png, png]


def test_manual_and_history_paths_preserve_original_group_after_selection_change(
    queue,
    config,
    frame,
    region,
):
    config.target, config.chat_id = chat().target, "seoul"
    first = queue.enqueue(encode_png(frame), region, "live", local_only=True)
    first_path = queue.image_path(first)
    assert first_path.parent.name.startswith("서울 돌봄팀--")
    config.target, config.chat_id = chat("부산 돌봄팀").target, "busan"
    second = queue.enqueue(encode_png(frame), region, "history", local_only=True)
    second_path = queue.image_path(second)
    assert second_path.parent.name.startswith("부산 돌봄팀--")
    assert queue.image_path(first) == first_path
    restarted = CaptureQueue(queue.root, config)
    assert restarted.stats()["unassigned"] == 2
    assert first_path.exists() and second_path.exists()
    restarted.bind_local(config.api_url, config.allow_local_http)
    first_job = restarted.claim(config.api_url)
    assert first_job["image_path"] == str(first_path)
    assert json.loads(first_job["metadata"])["chat_id"] == "seoul"
    restarted.acknowledge(first)
    restarted.maintain()
    assert not first_path.exists() and second_path.exists()


def test_capture_recovery_handles_group_files_without_touching_reply_queue(
    queue, config, frame, region
):
    config.target = chat().target
    capture_id = queue.enqueue(encode_png(frame), region, "live")
    folder = queue.image_path(capture_id).parent
    queue.image_path(capture_id).unlink()
    orphan = folder / "orphan.png"
    orphan.write_bytes(encode_png(frame))
    (folder / "partial.tmp").write_bytes(b"partial")
    jobs = ImageReplyQueue(queue)
    jobs.enqueue_pair("chat", encode_png(frame), encode_png(frame), folder=chat_folder_name(config))
    recovered = CaptureQueue(queue.root, config)
    assert recovered.stats()["failed"] == 1
    assert orphan.exists() and not (folder / "partial.tmp").exists()
    assert any("1 orphan PNGs" in message for message in recovered.recovery_messages)
    assert jobs.load_images(jobs.claim("chat")) == [encode_png(frame)] * 2

"""Durable ordered screenshot pairs for Run Agent (auto), separate from API uploads."""

import hashlib
import json
import os
import re
import shutil
import time

from app.models import AgentError, StorageFull
from app.storage.text_queue import TextQueue


class CaptureReviewRequired(AgentError):
    """One saved capture cannot be processed; later captures can still proceed."""


class ImageReplyQueue(TextQueue):
    table = "image_reply_queue"
    # Review is a side queue, never an eligible job or an ordering barrier.
    active_statuses = ("pending", "processing", "sending")
    # Reanalyzing the same immutable screenshots indefinitely cannot unblock FIFO.
    max_analysis_attempts = 3

    def __init__(self, storage):
        self.images = storage.images / "auto_catch"
        self.images.mkdir(parents=True, exist_ok=True)
        super().__init__(storage)
        self.maintain()

    def paths(self, payload):
        try:
            body = json.loads(payload)
            hashes = [body["before"], body["after"]]
            if not all(isinstance(h, str) and re.fullmatch("[0-9a-f]{64}", h) for h in hashes):
                raise ValueError()
            return [self.images / (h + ".png") for h in hashes]
        except (ValueError, KeyError, TypeError):
            raise AgentError("Queued screenshot metadata is invalid; review required") from None

    def enqueue_pair(self, chat_key, before, after):
        hashes = [hashlib.sha256(png).hexdigest() for png in (before, after)]
        with self.storage.lock:
            with self.storage.connect() as db:
                count = db.execute(
                    f"SELECT count(*) FROM {self.table} WHERE status IN ({self.status_placeholders})",
                    self.active_statuses,
                ).fetchone()[0]
            if count >= 1000:
                raise StorageFull(
                    "Run Agent (auto) has 1000 unfinished captures; collection stopped; queue retained"
                )
            files = {self.images / (h + ".png"): png for h, png in zip(hashes, (before, after))}
            needed = sum(len(png) for path, png in files.items() if not path.exists()) + 1024**2
            if self.storage.usage() + needed > self.storage.config.storage_limit_bytes:
                raise StorageFull(
                    "Run Agent (auto) storage limit reached; queued captures retained"
                )
            if shutil.disk_usage(self.images).free < needed + 32 * 1024**2:
                raise StorageFull(
                    "Disk space is low; Run Agent (auto) paused with queued captures retained"
                )
            for path, png in files.items():
                if path.exists():
                    if hashlib.sha256(path.read_bytes()).hexdigest() != path.stem:
                        raise AgentError(
                            "Stored Run Agent (auto) image changed; inspect local storage"
                        )
                    continue
                temporary = path.with_suffix(".tmp")
                try:
                    with temporary.open("wb") as file:
                        file.write(png)
                        file.flush()
                        os.fsync(file.fileno())
                    os.replace(temporary, path)
                finally:
                    temporary.unlink(missing_ok=True)
            # Commit the pair before advancing the capture baseline. Unknown commit
            # outcomes leave PNGs available for review rather than deleting them.
            job_id = super().enqueue(chat_key, json.dumps(dict(zip(("before", "after"), hashes))))
            return job_id, self.images / (hashes[1] + ".png")

    def load_images(self, job):
        try:
            result = []
            for path in self.paths(job["text"]):
                png = path.read_bytes()
                if hashlib.sha256(png).hexdigest() != path.stem:
                    raise ValueError()
                result.append(png)
            return result
        except (OSError, ValueError, AgentError):
            self.finish(job["job_id"], "review")
            raise CaptureReviewRequired(
                "Queued screenshot is missing, changed, or invalid; set aside for review; no reply sent"
            ) from None

    def finish(self, job_id, status):
        assert status in ("sent", "ignored", "review", "sending", "pending", "submitted")
        with self.storage.connect() as db:
            db.execute(f"UPDATE {self.table} SET status=? WHERE job_id=?", (status, job_id))

    def maintain(self):
        # Completed metadata expires in the parent constructor; live jobs always
        # retain both images. Old unreferenced files obey the same retention period.
        with self.storage.lock, self.storage.connect() as db:
            referenced = set()
            for row in db.execute(f"SELECT text FROM {self.table} WHERE text<>''"):
                try:
                    referenced.update(self.paths(row["text"]))
                except AgentError:
                    # Preserve every file if metadata cannot safely establish references.
                    return
            cutoff = time.time() - self.storage.config.metadata_retention_days * 86400
            for path in self.images.glob("*.png"):
                if path not in referenced and path.stat().st_mtime < cutoff:
                    path.unlink()
            for path in self.images.glob("*.tmp"):
                path.unlink(missing_ok=True)

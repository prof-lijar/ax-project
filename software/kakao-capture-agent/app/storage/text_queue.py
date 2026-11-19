"""Persistent FIFO for observed text batches. Sending is never replayed after a crash."""

import time
from uuid import uuid4

from app.models import AgentError, StorageFull


class TextQueue:
    table = "text_reply_queue"
    active_statuses = ("pending", "processing", "sending", "review")
    max_analysis_attempts = None

    def __init__(self, storage):
        if self.table not in {"text_reply_queue", "image_reply_queue"}:
            raise ValueError("Unsupported reply queue table")
        self.storage = storage
        self.status_placeholders = ",".join("?" for _ in self.active_statuses)
        with storage.connect() as db:
            db.executescript(f"""
                CREATE TABLE IF NOT EXISTS {self.table} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL UNIQUE,
                    chat_key TEXT NOT NULL,
                    text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt REAL NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS {self.table}_pending ON {self.table}(chat_key, status, id);
            """)
            db.execute(f"UPDATE {self.table} SET status='pending' WHERE status='processing'")
            db.execute(f"UPDATE {self.table} SET status='review' WHERE status='sending'")
            db.execute(
                f"DELETE FROM {self.table} WHERE status IN ('sent','ignored','submitted') AND created_at<?",
                (time.time() - storage.config.metadata_retention_days * 86400,),
            )

    def enqueue(self, chat_key, text):
        with self.storage.lock:
            if self.storage.usage() >= self.storage.config.storage_limit_bytes:
                raise StorageFull(
                    "Reply queue storage limit reached; collection stopped; previously queued text retained"
                )
            with self.storage.connect() as db:
                count = db.execute(
                    f"SELECT count(*) FROM {self.table} WHERE status IN ({self.status_placeholders})",
                    self.active_statuses,
                ).fetchone()[0]
                if count >= 1000:
                    raise StorageFull("Reply queue has 1000 unfinished batches; stopped collecting")
                job_id = str(uuid4())
                db.execute(
                    f"INSERT INTO {self.table}(job_id,chat_key,text,status,created_at) VALUES(?,?,?,'pending',?)",
                    (job_id, chat_key, text, time.time()),
                )
                return job_id

    def claim(self, chat_key):
        with self.storage.lock, self.storage.connect() as db:
            if self.max_analysis_attempts is not None:
                # Also unblock queues saved by versions that retried forever,
                # regardless of their old backoff deadline. Never touch sends.
                db.execute(
                    f"UPDATE {self.table} SET status='review',next_attempt=0 "
                    "WHERE chat_key=? AND status='pending' AND attempts>=?",
                    (chat_key, self.max_analysis_attempts),
                )
            row = db.execute(
                f"SELECT * FROM {self.table} WHERE chat_key=? AND status IN ({self.status_placeholders}) ORDER BY id LIMIT 1",
                (chat_key, *self.active_statuses),
            ).fetchone()
            if row is None:
                return None
            if row["status"] == "review":
                raise AgentError(
                    "A previous reply has uncertain delivery; inspect the selected chat, "
                    "click Review Replies to mark that attempt handled without resending, "
                    "then click Run Agent (auto) to resume the remaining queue"
                )
            if row["status"] != "pending" or row["next_attempt"] > time.time():
                return None
            db.execute(
                f"UPDATE {self.table} SET status='processing' WHERE job_id=?", (row["job_id"],)
            )
            return dict(row)

    def count(self, chat_key):
        with self.storage.connect() as db:
            return db.execute(
                f"SELECT count(*) FROM {self.table} WHERE chat_key=? AND status IN ({self.status_placeholders})",
                (chat_key, *self.active_statuses),
            ).fetchone()[0]

    def review_count(self, chat_key):
        with self.storage.connect() as db:
            return db.execute(
                f"SELECT count(*) FROM {self.table} WHERE chat_key=? AND status='review'",
                (chat_key,),
            ).fetchone()[0]

    def finish(self, job_id, status):
        assert status in ("sent", "ignored", "review", "sending", "pending")
        with self.storage.connect() as db:
            db.execute(
                f"UPDATE {self.table} SET status=?, text=CASE WHEN ? IN ('sent','ignored') THEN '' ELSE text END WHERE job_id=?",
                (status, status, job_id),
            )

    def retry(self, job_id):
        with self.storage.lock, self.storage.connect() as db:
            attempts = (
                db.execute(
                    f"SELECT attempts FROM {self.table} WHERE job_id=?", (job_id,)
                ).fetchone()[0]
                + 1
            )
            if self.max_analysis_attempts is not None and attempts >= self.max_analysis_attempts:
                db.execute(
                    f"UPDATE {self.table} SET status='review',attempts=?,next_attempt=0 WHERE job_id=?",
                    (attempts, job_id),
                )
                return None
            delay = min(2 ** min(attempts, 5), 30)
            db.execute(
                f"UPDATE {self.table} SET status='pending',attempts=?,next_attempt=? WHERE job_id=?",
                (attempts, time.time() + delay, job_id),
            )
            return delay

    def resolve_review(self, chat_key):
        with self.storage.connect() as db:
            db.execute(
                f"UPDATE {self.table} SET status='ignored',text='' WHERE chat_key=? AND status='review'",
                (chat_key,),
            )

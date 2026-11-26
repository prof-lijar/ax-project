"""Durable per-capture plan and external-action receipts, independent of reply delivery."""

import json
from uuid import uuid4

from app.models import Cancelled


class OperationJournal:
    def __init__(self, storage):
        self.storage = storage
        with storage.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS operation_journal (key TEXT PRIMARY KEY, job_id TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            # Screenshot queue retention is the authority for how long receipts live.
            db.execute(
                "DELETE FROM operation_journal WHERE job_id NOT IN (SELECT job_id FROM image_reply_queue)"
            )

    def get(self, key):
        with self.storage.connect() as db:
            row = db.execute("SELECT payload FROM operation_journal WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def claim(self, key, job_id, payload):
        with self.storage.connect() as db:
            return (
                db.execute(
                    "INSERT OR IGNORE INTO operation_journal(key,job_id,payload) VALUES(?,?,?)",
                    (key, job_id, json.dumps(payload, ensure_ascii=False)),
                ).rowcount
                == 1
            )

    def complete(self, key, payload):
        with self.storage.connect() as db:
            db.execute(
                "UPDATE operation_journal SET payload=? WHERE key=?",
                (json.dumps(payload, ensure_ascii=False), key),
            )

    def queue_requests(self, job_id, plan):
        """Commit one job per request before the first external action, in capture order."""
        with self.storage.lock, self.storage.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            capture = db.execute(
                "SELECT * FROM image_reply_queue WHERE job_id=? AND status='processing'", (job_id,)
            ).fetchone()
            if capture is None:
                raise Cancelled("Capture is no longer being processed")
            if db.execute("SELECT 1 FROM operation_journal WHERE key=?", (job_id + ":plan",)).fetchone():
                return
            for index, request in enumerate(plan):
                task_id = job_id
                if index:
                    task_id = str(uuid4())
                    db.execute(
                        "INSERT INTO image_reply_queue(job_id,chat_key,text,status,created_at,parent_capture_id) "
                        "VALUES(?,?,?,'pending',?,?)",
                        (task_id, capture["chat_key"], capture["text"], capture["created_at"], capture["id"]),
                    )
                    db.execute(
                        "INSERT INTO operation_journal(key,job_id,payload) "
                        "SELECT ?,?,payload FROM operation_journal WHERE key=?",
                        (task_id + ":sms-routing", task_id, job_id + ":sms-routing"),
                    )
                db.execute(
                    "INSERT INTO operation_journal(key,job_id,payload) VALUES(?,?,?)",
                    (task_id + ":plan", task_id, json.dumps([request], ensure_ascii=False)),
                )

    def reopen_skipped_image(self, job_id, result_key, saved):
        """Reclassify a legacy negative image test only if it never claimed an API call."""
        with self.storage.lock, self.storage.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM operation_journal WHERE job_id=? AND key LIKE '%:api'", (job_id,)
            ).fetchone():
                return False
            row = db.execute(
                "SELECT payload FROM operation_journal WHERE key=? AND job_id=?", (result_key, job_id)
            ).fetchone()
            if (json.loads(row[0]) if row else None) != saved:
                return False
            db.execute("DELETE FROM operation_journal WHERE job_id=?", (job_id,))
            db.execute("UPDATE image_reply_queue SET status='pending' WHERE job_id=?", (job_id,))
            return True

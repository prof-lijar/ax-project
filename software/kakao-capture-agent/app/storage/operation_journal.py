"""Durable per-capture plan and external-action receipts, independent of reply delivery."""

import json


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

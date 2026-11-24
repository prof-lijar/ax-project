"""Durable per-capture plan and external-action receipts, independent of reply delivery."""

import json
import unicodedata


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

    def previously_attempted(self, chat_key, request, job_id):
        """Startup must not rerun a visible request with an existing API claim.

        Scope to the same chat/destination and retained captures. Ordinary new
        message events remain eligible, even when their text repeats.
        """
        def signature(value):
            if value.get("workflow_id") == "new_installation":
                return ("new_installation", "".join(unicodedata.normalize("NFKC", value["message"]).split()))
            return tuple(
                "".join(unicodedata.normalize("NFKC", value[key]).split())
                for key in ("message", "action", "name", "address")
            )

        with self.storage.connect() as db:
            rows = db.execute(
                "SELECT a.payload FROM operation_journal a "
                "JOIN operation_journal r ON r.key=substr(a.key,1,length(a.key)-9)||':api' "
                "JOIN image_reply_queue q ON q.job_id=a.job_id "
                "WHERE a.key LIKE '%:analysis' AND q.chat_key=? AND a.job_id<>?",
                (chat_key, job_id),
            ).fetchall()
        for row in rows:
            previous = json.loads(row["payload"]).get("request")
            if previous and signature(previous) == signature(request):
                return True
        return False

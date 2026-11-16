"""Single-process, thread-safe durable queue; each transaction owns its connection."""

import hashlib
import json
import os
import shutil
import sqlite3
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.models import StorageFull


class CaptureQueue:
    def __init__(self, root, config):
        self.root, self.config = Path(root), config
        self.images = self.root / "captures"
        self.images.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "queue.db"
        self.lock = threading.RLock()
        self.session_id = str(uuid4())
        self.sequence = 0
        self.last_maintenance = 0
        self.recovery_messages = []
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("Unsupported queue schema version")
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(Path(__file__).with_name("schema.sql").read_text())
        self.recover()

    def connect(self):
        # Contextlib wrapper closes connections as well as committing/rolling back.
        from contextlib import contextmanager

        @contextmanager
        def connection():
            db = sqlite3.connect(self.path, timeout=10)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA synchronous=FULL")
            try:
                with db:
                    yield db
            finally:
                db.close()

        return connection()

    def event(self, kind, detail):
        with self.lock, self.connect() as db:
            db.execute(
                "INSERT INTO events(created_at,kind,detail) VALUES(?,?,?)",
                (time.time(), kind, detail),
            )

    def usage(self):
        total = 0
        with self.lock:
            for path in self.root.rglob("*"):
                try:
                    if path.is_file():
                        total += path.stat().st_size
                except FileNotFoundError:
                    pass  # Log rotation can run concurrently.
        return total

    def enqueue(self, png, region, mode, timestamp=None):
        with self.lock:
            if time.monotonic() - self.last_maintenance >= 30:
                self.maintain()
            # Reserve room for SQLite/WAL and diagnostics as well as the PNG.
            needed = len(png) + 1024 * 1024
            if self.usage() + needed > self.config.storage_limit_bytes:
                raise StorageFull("Local storage limit reached; pending captures are retained")
            if shutil.disk_usage(self.root).free < needed + 32 * 1024**2:
                raise StorageFull("Disk space is low; capture paused")
            capture_id = str(uuid4())
            timestamp = timestamp or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            self.sequence += 1
            metadata = {
                "capture_id": capture_id,
                "device_id": self.config.device_id,
                "chat_id": self.config.chat_id,
                "timestamp": timestamp,
                "capture_mode": mode,
                "image_hash": hashlib.sha256(png).hexdigest(),
                "region": asdict(region),
                "sequence_number": self.sequence,
            }
            path = self.images / f"{capture_id}.png"
            temporary = path.with_suffix(".tmp")
            try:
                with temporary.open("wb") as file:
                    file.write(png)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary, path)
                with self.connect() as db:
                    db.execute(
                        """INSERT INTO capture_queue
                        (capture_id,timestamp,image_path,image_hash,capture_mode,destination,
                         allow_local_http,metadata,created_at)
                        VALUES(?,?,?,?,?,?,?,?,?)""",
                        (
                            capture_id,
                            timestamp,
                            str(path),
                            metadata["image_hash"],
                            mode,
                            self.config.api_url,
                            self.config.allow_local_http,
                            json.dumps(metadata),
                            time.time(),
                        ),
                    )
                    db.execute(
                        "INSERT INTO events(created_at,kind,detail) VALUES(?,?,?)",
                        (
                            time.time(),
                            "capture",
                            json.dumps(
                                {
                                    "capture_id": capture_id,
                                    "session_id": self.session_id,
                                    "sequence": self.sequence,
                                }
                            ),
                        ),
                    )
            except BaseException:
                # Unknown commit outcomes are reconciled, never delete a possibly committed image.
                temporary.unlink(missing_ok=True)
                raise
            return capture_id

    def recover(self):
        with self.lock, self.connect() as db:
            db.execute(
                "UPDATE capture_queue SET upload_status='pending' WHERE upload_status='uploading'"
            )
            rows = db.execute(
                "SELECT capture_id,image_path,upload_status FROM capture_queue"
            ).fetchall()
            known = {Path(r["image_path"]).name for r in rows}
            for row in rows:
                if row["upload_status"] != "uploaded" and not Path(row["image_path"]).exists():
                    self.recovery_messages.append(
                        "Queued image is missing; operator review required"
                    )
                    db.execute(
                        "UPDATE capture_queue SET upload_status='failed',last_error=? WHERE capture_id=?",
                        ("Image file missing; operator review required", row["capture_id"]),
                    )
            for path in self.images.glob("*.tmp"):
                path.unlink()
            orphans = [p for p in self.images.glob("*.png") if p.name not in known]
            if orphans:
                self.recovery_messages.append(
                    f"{len(orphans)} orphan PNGs retained for operator review"
                )
                db.execute(
                    "INSERT INTO events(created_at,kind,detail) VALUES(?,?,?)",
                    (time.time(), "recovery", f"{len(orphans)} orphan PNGs retained for review"),
                )

    def claim(self, destination):
        if not destination:
            return None
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """SELECT * FROM capture_queue WHERE upload_status='pending'
                AND next_attempt<=? AND destination=? ORDER BY created_at LIMIT 1""",
                (time.time(), destination),
            ).fetchone()
            if row:
                db.execute(
                    "UPDATE capture_queue SET upload_status='uploading' WHERE capture_id=?",
                    (row["capture_id"],),
                )
                return dict(row)
        return None

    def acknowledge(self, capture_id):
        with self.lock, self.connect() as db:
            db.execute(
                "UPDATE capture_queue SET upload_status='uploaded',uploaded_at=?,last_error=NULL WHERE capture_id=?",
                (time.time(), capture_id),
            )

    def release(self, capture_id):
        """Recover an uncertain upload/ack transaction using the same idempotency key."""
        with self.lock, self.connect() as db:
            db.execute(
                "UPDATE capture_queue SET upload_status='pending' WHERE capture_id=? AND upload_status='uploading'",
                (capture_id,),
            )

    def fail(self, capture_id, message, retry_count, delay=None):
        with self.lock, self.connect() as db:
            db.execute(
                """UPDATE capture_queue SET upload_status=?,retry_count=?,next_attempt=?,
                last_error=? WHERE capture_id=?""",
                (
                    "pending" if delay is not None else "failed",
                    retry_count,
                    time.time() + (delay or 0),
                    message,
                    capture_id,
                ),
            )

    def retry_failed(self, destination):
        with self.lock, self.connect() as db:
            db.execute(
                """UPDATE capture_queue SET upload_status='pending',retry_count=0,next_attempt=0
                WHERE upload_status='failed' AND destination=?""",
                (destination,),
            )

    def bind_local(self, destination, allow_local_http):
        """Explicit operator action; only captures created with no endpoint are eligible."""
        with self.lock, self.connect() as db:
            db.execute(
                "UPDATE capture_queue SET destination=?,allow_local_http=? WHERE destination=''",
                (destination, allow_local_http),
            )

    def stats(self):
        with self.lock, self.connect() as db:
            result = dict(
                db.execute(
                    "SELECT upload_status,count(*) FROM capture_queue GROUP BY upload_status"
                )
            )
            result["last_upload"] = db.execute(
                "SELECT max(uploaded_at) FROM capture_queue"
            ).fetchone()[0]
            result["unassigned"] = db.execute(
                "SELECT count(*) FROM capture_queue WHERE destination='' "
            ).fetchone()[0]
            result["other_destination"] = db.execute(
                "SELECT count(*) FROM capture_queue WHERE destination!=? AND destination!='' AND upload_status!='uploaded'",
                (self.config.api_url,),
            ).fetchone()[0]
        result["bytes"] = self.usage()
        return result

    def maintain(self):
        with self.lock, self.connect() as db:
            now = time.time()
            rows = db.execute(
                "SELECT capture_id,image_path FROM capture_queue WHERE upload_status='uploaded' AND image_deleted=0 AND uploaded_at<=?",
                (now - self.config.uploaded_retention_hours * 3600,),
            ).fetchall()
            for row in rows:
                Path(row["image_path"]).unlink(missing_ok=True)
                db.execute(
                    "UPDATE capture_queue SET image_deleted=1 WHERE capture_id=?",
                    (row["capture_id"],),
                )
            cutoff = now - self.config.metadata_retention_days * 86400
            # Keep metadata while an image is still retained.
            for row in db.execute(
                "SELECT capture_id,image_path FROM capture_queue WHERE upload_status='uploaded' AND uploaded_at<?",
                (cutoff,),
            ).fetchall():
                if not Path(row["image_path"]).exists():
                    db.execute("DELETE FROM capture_queue WHERE capture_id=?", (row["capture_id"],))
            db.execute("DELETE FROM events WHERE created_at<?", (cutoff,))
        self.last_maintenance = time.monotonic()

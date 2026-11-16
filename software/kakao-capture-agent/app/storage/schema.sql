CREATE TABLE IF NOT EXISTS capture_queue (
    capture_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    image_path TEXT NOT NULL,
    image_hash TEXT NOT NULL,
    capture_mode TEXT NOT NULL,
    destination TEXT NOT NULL,
    allow_local_http INTEGER NOT NULL,
    metadata TEXT NOT NULL,
    upload_status TEXT NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0,
    next_attempt REAL NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    uploaded_at REAL,
    image_deleted INTEGER NOT NULL DEFAULT 0,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS queue_ready ON capture_queue(upload_status, next_attempt);
CREATE INDEX IF NOT EXISTS queue_retention ON capture_queue(upload_status, image_deleted, uploaded_at);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    kind TEXT NOT NULL,
    detail TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS event_retention ON events(created_at);
PRAGMA user_version = 1;

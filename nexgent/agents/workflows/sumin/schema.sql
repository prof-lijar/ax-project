CREATE SCHEMA IF NOT EXISTS sumin;
CREATE TABLE IF NOT EXISTS sumin.events (
    key text PRIMARY KEY,
    payload jsonb NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','completed','failed')),
    attempts integer NOT NULL DEFAULT 0,
    available_at timestamptz NOT NULL DEFAULT NOW(),
    lease_token uuid,
    lease_until timestamptz,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS sumin_events_claim ON sumin.events(status, available_at);
CREATE TABLE IF NOT EXISTS sumin.channels (
    team_id text NOT NULL,
    channel_id text NOT NULL,
    folder text NOT NULL UNIQUE,
    PRIMARY KEY (team_id, channel_id)
);
CREATE TABLE IF NOT EXISTS sumin.files (
    team_id text NOT NULL,
    channel_id text NOT NULL,
    file_id text NOT NULL,
    path text NOT NULL UNIQUE,
    PRIMARY KEY (team_id, channel_id, file_id)
);
CREATE TABLE IF NOT EXISTS sumin.contexts (
    team_id text NOT NULL,
    channel_id text NOT NULL,
    file_id text NOT NULL,
    event_id text NOT NULL,
    message_text text NOT NULL,
    PRIMARY KEY (team_id, channel_id, file_id, event_id)
);

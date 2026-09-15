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

-- The operator is clearing the old Nextcloud archive. Remap database paths
-- without deleting files, changing event statuses, or replaying completed work.
CREATE TABLE IF NOT EXISTS sumin.migrations (
    name text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT NOW()
);
DO $$
DECLARE
    mapping record;
    new_folder text;
BEGIN
    LOCK TABLE sumin.migrations IN EXCLUSIVE MODE;
    IF NOT EXISTS (SELECT 1 FROM sumin.migrations WHERE name='channel-folders-v2') THEN
        LOCK TABLE sumin.channels, sumin.files IN EXCLUSIVE MODE;
        FOR mapping IN SELECT * FROM sumin.channels LOOP
            IF split_part(mapping.folder, '/', -2) = mapping.team_id THEN
                new_folder := regexp_replace(mapping.folder, '/[^/]+/([^/]+)$', '/\1');
                UPDATE sumin.files
                SET path = new_folder || substring(path FROM length(mapping.folder) + 1)
                WHERE team_id=mapping.team_id AND channel_id=mapping.channel_id
                    AND left(path, length(mapping.folder) + 1) = mapping.folder || '/';
                UPDATE sumin.channels SET folder=new_folder
                WHERE team_id=mapping.team_id AND channel_id=mapping.channel_id;
            END IF;
        END LOOP;
        INSERT INTO sumin.migrations(name) VALUES('channel-folders-v2');
    END IF;
END $$;

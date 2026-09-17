CREATE SCHEMA IF NOT EXISTS agent;

-- Move legacy tables in place, retaining rows, indexes, constraints and grants.
-- The caller executes this entire script in one transaction with consumers stopped.
DO $$
DECLARE
    table_name text;
    index_name text;
BEGIN
    PERFORM pg_advisory_xact_lock(73686421);
    FOREACH table_name IN ARRAY ARRAY['events', 'channels', 'files', 'contexts', 'migrations'] LOOP
        IF to_regclass(format('sumin.%I', table_name)) IS NOT NULL THEN
            IF to_regclass(format('agent.%I', 'sumin_' || table_name)) IS NOT NULL
                OR to_regclass(format('sumin.%I', 'sumin_' || table_name)) IS NOT NULL THEN
                RAISE EXCEPTION 'Sumin schema migration conflict for table %', table_name;
            END IF;
        END IF;
    END LOOP;
    FOREACH table_name IN ARRAY ARRAY['events', 'channels', 'files', 'contexts', 'migrations'] LOOP
        IF to_regclass(format('sumin.%I', table_name)) IS NOT NULL THEN
            -- Index names are schema-wide: avoid collisions with other agents.
            FOR index_name IN
                SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
                WHERE i.indrelid=to_regclass(format('sumin.%I', table_name))
            LOOP
                IF left(index_name, 6) <> 'sumin_' THEN
                    EXECUTE format('ALTER INDEX sumin.%I RENAME TO %I', index_name, 'sumin_' || index_name);
                END IF;
            END LOOP;
            EXECUTE format('ALTER TABLE sumin.%I RENAME TO %I', table_name, 'sumin_' || table_name);
            EXECUTE format('ALTER TABLE sumin.%I SET SCHEMA agent', 'sumin_' || table_name);
        END IF;
    END LOOP;
END $$;

CREATE TABLE IF NOT EXISTS agent.sumin_events (
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
CREATE INDEX IF NOT EXISTS sumin_events_claim ON agent.sumin_events(status, available_at);
CREATE TABLE IF NOT EXISTS agent.sumin_channels (
    team_id text NOT NULL,
    channel_id text NOT NULL,
    folder text NOT NULL UNIQUE,
    PRIMARY KEY (team_id, channel_id)
);
CREATE TABLE IF NOT EXISTS agent.sumin_files (
    team_id text NOT NULL,
    channel_id text NOT NULL,
    file_id text NOT NULL,
    path text NOT NULL UNIQUE,
    PRIMARY KEY (team_id, channel_id, file_id)
);
CREATE TABLE IF NOT EXISTS agent.sumin_contexts (
    team_id text NOT NULL,
    channel_id text NOT NULL,
    file_id text NOT NULL,
    event_id text NOT NULL,
    message_text text NOT NULL,
    PRIMARY KEY (team_id, channel_id, file_id, event_id)
);

-- The operator is clearing the old Nextcloud archive. Remap database paths
-- without deleting files, changing event statuses, or replaying completed work.
CREATE TABLE IF NOT EXISTS agent.sumin_migrations (
    name text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT NOW()
);
DO $$
DECLARE
    mapping record;
    new_folder text;
BEGIN
    LOCK TABLE agent.sumin_migrations IN EXCLUSIVE MODE;
    IF NOT EXISTS (SELECT 1 FROM agent.sumin_migrations WHERE name='channel-folders-v2') THEN
        LOCK TABLE agent.sumin_channels, agent.sumin_files IN EXCLUSIVE MODE;
        FOR mapping IN SELECT * FROM agent.sumin_channels LOOP
            IF split_part(mapping.folder, '/', -2) = mapping.team_id THEN
                new_folder := regexp_replace(mapping.folder, '/[^/]+/([^/]+)$', '/\1');
                UPDATE agent.sumin_files
                SET path = new_folder || substring(path FROM length(mapping.folder) + 1)
                WHERE team_id=mapping.team_id AND channel_id=mapping.channel_id
                    AND left(path, length(mapping.folder) + 1) = mapping.folder || '/';
                UPDATE agent.sumin_channels SET folder=new_folder
                WHERE team_id=mapping.team_id AND channel_id=mapping.channel_id;
            END IF;
        END LOOP;
        INSERT INTO agent.sumin_migrations(name) VALUES('channel-folders-v2');
    END IF;
END $$;

-- Search metadata: real upload time when available; legacy records remain unknown.
ALTER TABLE agent.sumin_files ADD COLUMN IF NOT EXISTS original_name text;
ALTER TABLE agent.sumin_files ADD COLUMN IF NOT EXISTS uploaded_at timestamptz;
ALTER TABLE agent.sumin_files ADD COLUMN IF NOT EXISTS uploader_id text;

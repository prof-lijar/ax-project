-- LOCAL archive database only. Existing archive reports and constraints are retained.
-- Do not apply to production or copy/move historical ansimk reports implicitly.
CREATE TABLE IF NOT EXISTS archive.resources_ward_weekly_report (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    ward_id         BIGINT NOT NULL
                    REFERENCES archive.resources_ward(id)
                    ON DELETE RESTRICT,

    week_start_date DATE NOT NULL,
    week_end_date   DATE NOT NULL,

    weekly_score    SMALLINT,
    weekly_status   VARCHAR(20),

    report_data     JSONB NOT NULL,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (ward_id, week_start_date)
);

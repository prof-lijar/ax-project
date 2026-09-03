CREATE TABLE ansimk.ward_weekly_report (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    ward_id         BIGINT NOT NULL
                    REFERENCES ansimk.resources_ward(id)
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

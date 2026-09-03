from pathlib import Path

_MIGRATION = (
    Path(__file__).parents[2]
    / "workflows"
    / "weekly_report"
    / "source"
    / "migrations"
    / "001_create_ward_weekly_report.sql"
)


def test_weekly_report_storage_schema_matches_approved_contract() -> None:
    sql = _MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE ansimk.ward_weekly_report" in sql
    assert "BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY" in sql
    assert "REFERENCES ansimk.resources_ward(id)" in sql
    assert "ON DELETE RESTRICT" in sql
    assert "week_start_date DATE NOT NULL" in sql
    assert "week_end_date   DATE NOT NULL" in sql
    assert "weekly_score    SMALLINT" in sql
    assert "weekly_status   VARCHAR(20)" in sql
    assert "report_data     JSONB NOT NULL" in sql
    assert "created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()" in sql
    assert "updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()" in sql
    assert "UNIQUE (ward_id, week_start_date)" in sql

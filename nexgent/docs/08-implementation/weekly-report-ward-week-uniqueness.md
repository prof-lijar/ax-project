# Weekly Report Ward/Week Uniqueness

Date: 2026-09-08

The existing bulk report writer already implements one durable row per
`(ward_id, week_start_date)` in `ansimk.resources_ward_weekly_report`.
Requests require Monday week starts. Migration `001` declares the unique
constraint, and the writer uses `ON CONFLICT ... DO UPDATE` to replace the
end date, score, status, and JSON report and advance `updated_at`. The row ID
and `created_at` remain unchanged. Different wards and weeks retain separate
rows. No production persistence code or schema changes were necessary.

Added `agents/tests/integration/test_weekly_report_storage_postgres.py` to
exercise the actual migration and writer SQL against session-local temporary
tables. It checks repeated saves, duplicates within a batch, concurrent callers
sharing a single-connection pool, preservation of row identity, replacement
of content, and independent ward/week keys. It does not test simultaneous
writes across separate database connections. No real ward/report tables are
modified by this test.

Validation from `agents/`:

```bash
UV_CACHE_DIR=/tmp/nexgent-uv-cache uv run --no-sync pytest tests/unit/test_weekly_report_storage.py tests/contract/test_weekly_report_storage_schema.py tests/integration/test_weekly_report_storage_postgres.py
UV_CACHE_DIR=/tmp/nexgent-uv-cache uv run --no-sync ruff check tests/integration/test_weekly_report_storage_postgres.py
```

Result: four tests passed, one PostgreSQL integration test skipped; lint
passed. Offline `uv sync --frozen --offline` could not resolve uncached
`hatchling`, so validation used the existing virtual environment.

The PostgreSQL test requires `WEEKLY_REPORT_TEST_DATABASE_DSN`. No test DSN
was configured, and local Docker access was denied. Remaining verification:

```bash
cd agents
WEEKLY_REPORT_TEST_DATABASE_DSN='postgresql://USER:PASSWORD@HOST/TEST_DATABASE' UV_CACHE_DIR=/tmp/nexgent-uv-cache uv run --no-sync pytest tests/integration/test_weekly_report_storage_postgres.py
```

The deployed schema and existing report data were not inspected or modified.
If duplicates are observed there, check the actual unique constraint, deployed
writer version, and week start values. A read-only duplicate check is:

```sql
SELECT ward_id, week_start_date, count(*)
FROM ansimk.resources_ward_weekly_report
GROUP BY ward_id, week_start_date
HAVING count(*) > 1;
```

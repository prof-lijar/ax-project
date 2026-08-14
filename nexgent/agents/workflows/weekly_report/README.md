# `ansimk_weekly_reporter`

This manually triggered LangGraph workflow reads daily ward-danger records
through the database MCP, compares a requested Monday-to-Monday week with its
preceding week, and returns Korean Markdown reports for a bounded ward subset.
It is an end-to-end prototype for validating the MCP, model, graph, and output
path before final business requirements are defined.

Python calculates every danger-day count and delta. The configured
OpenAI-compatible model receives validated metrics and may write only
digit-free narrative text. A missing, failed, empty, or invalid model response
uses a disclosed deterministic Korean fallback without failing other reports.

## Input and local run

```json
{
  "week_start": "2026-08-03",
  "timezone": "Asia/Seoul"
}
```

`week_start` must be a Monday. The current and previous seven-day periods are
half-open. Run the verified demo cycle with:

```bash
uv run --env-file .env python playground/weekly_report.py --week-start 2026-08-03
```

The ignored `.env` must provide `DB_MCP_SERVER_BEARER_TOKEN`. Model settings
use `OPENAI_BASE_URL`, `OPENAI_MODEL`, and `OPENAI_API_KEY` or their supported
aliases. The runner bounds LangGraph concurrency to four.

## Database MCP source

The repository defaults to:

- server: `db_mcp_server`
- schema: `ansimk`
- table: `analysis_warddangerdaily`
- demo batch: three wards

Only the MCP `query_data` read tool is granted. The first bounded query selects
ward identities with danger records in the fourteen-day window. A second query
retrieves complete `ward_id`, `date`, and `first_at` histories for the selected
wards. Every untrusted MCP result is validated before entering graph state.

Configure the source with `WEEKLY_REPORT_MCP_SERVER`,
`WEEKLY_REPORT_MCP_SCHEMA`, and `WEEKLY_REPORT_MCP_TABLE`. Set
`WEEKLY_REPORT_MAX_WARDS` between one and twenty-five; the prototype defaults
to three and emits a warning when it reports only a subset. The checked-in
mock repository is used only by deterministic tests.

The live cycle on 2026-08-14 generated three AI-narrated reports for the week
starting 2026-08-03. This prototype intentionally reports only danger-day
counts. Risk semantics, subject naming, prioritization, dispatch joins,
delivery, scheduling, and persistence require product validation before real
use.

The workflow remains registered as `ansimk_weekly_reporter` in
`langgraph.json`; it performs no database write or delivery operation.

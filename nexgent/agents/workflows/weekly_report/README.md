# `ansimk_weekly_reporter`

This manually triggered LangGraph workflow loads a deterministic three-user
work-activity scenario, compares the requested Monday-to-Monday week with its
preceding week, and returns one Korean Markdown report per user.

Calculations are pure Python. The configured OpenAI-compatible model receives
validated metrics and may write only digit-free narrative text. A missing,
failed, empty, or invalid model response produces a complete deterministic
Korean fallback report and a batch warning; one user's model failure never
fails the other reports.

## Input

```json
{
  "week_start": "2026-08-03",
  "timezone": "Asia/Seoul"
}
```

`week_start` must be a Monday. The reporting interval is half-open: local
Monday at the start date through the following Monday, excluding the end date.
The previous seven days form the comparison period.

## Run locally

```bash
uv run python playground/weekly_report.py --week-start 2026-08-03
```

Set `OPENAI_BASE_URL`, `OPENAI_MODEL`, and `OPENAI_API_KEY` to use model-backed
narratives. The command still succeeds without them by exercising the fallback
path. The runner sets LangGraph's `max_concurrency` to four.

The workflow is registered as `ansimk_weekly_reporter` in `langgraph.json`.
Agent Server owns durable checkpoints and thread identity. Scheduling, a real
database adapter, report persistence, authentication, and delivery channels are
future integration work; no external write or send operation occurs in v1.

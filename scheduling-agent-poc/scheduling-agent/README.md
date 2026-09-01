# scheduling-agent

Date: 2026-08-28 (Asia/Seoul)

Updated: 2026-08-31 (Asia/Seoul) — Scout systemd supervision status.

Simple ReAct agent
Agent generated with `agents-cli` version `1.4.1`

## Project Structure

```
scheduling-agent/
├── app/         # Core agent code
│   ├── agent.py               # Main agent logic
│   ├── fast_api_app.py        # FastAPI Backend server
│   └── app_utils/             # App utilities and helpers
├── tests/                     # Unit, integration, and load tests
├── GEMINI.md                  # AI-assisted development guide
└── pyproject.toml             # Project dependencies
```

> 💡 **Tip:** Use [Antigravity CLI](https://antigravity.google/) for AI-assisted development - project context is pre-configured in `GEMINI.md`.

## Requirements

Before you begin, ensure you have:
- **uv**: Python package manager (used for all dependency management in this project) - [Install](https://docs.astral.sh/uv/getting-started/installation/) ([add packages](https://docs.astral.sh/uv/concepts/dependencies/) with `uv add <package>`)
- **agents-cli**: Agents CLI - Install with `uv tool install google-agents-cli`
- **Google Cloud SDK**: For GCP services - [Install](https://cloud.google.com/sdk/docs/install)


## Quick Start

Install `agents-cli` and its skills if not already installed:

```bash
uvx google-agents-cli setup
```

Install required packages:

```bash
agents-cli install
```

Test the agent with a local web server:

```bash
agents-cli playground
```

You can also use features from the [ADK](https://adk.dev/) CLI with `uv run adk`.

## Commands

| Command              | Description                                                                                 |
| -------------------- | ------------------------------------------------------------------------------------------- |
| `agents-cli install` | Install dependencies using uv                                                         |
| `agents-cli playground` | Launch local development environment                                                  |
| `agents-cli lint`    | Run code quality checks                                                               |
| `agents-cli eval`    | Evaluate agent behavior (generate, grade, analyze, and more — see `agents-cli eval --help`) |
| `uv run pytest tests/unit tests/integration` | Run unit and integration tests                                                        || [A2A Inspector](https://github.com/a2aproject/a2a-inspector) | Launch A2A Protocol Inspector                                                        |

## 🛠️ Project Management

| Command | What It Does |
|---------|--------------|
| `agents-cli scaffold enhance` | Add CI/CD pipelines and Terraform infrastructure |
| `agents-cli infra cicd` | One-command setup of entire CI/CD pipeline + infrastructure |
| `agents-cli scaffold upgrade` | Auto-upgrade to latest version while preserving customizations |

---

## Development

Edit your agent logic in `app/agent.py` and test with `agents-cli playground` - it auto-reloads on save.

## Deployment

```bash
gcloud config set project <your-project-id>
agents-cli deploy
```

To add CI/CD and Terraform, run `agents-cli scaffold enhance`.
To set up your production infrastructure, run `agents-cli infra cicd`.

## Persistent Scout Scheduling API

The standalone FastAPI application now owns two logically separate schedulers:

- the existing in-memory legacy scheduler used by the calculator and Worker
  Agent POC; and
- a persistent Scout scheduler whose only callback is the existing Scout HTTP
  contract at `POST /v1/scout/runs`.

The Scout path does not invoke `calculator_worker_agent` and does not duplicate
Scout research logic. SQLite stores schedule history and APScheduler jobs. A
requested `run_at` is an Asia/Seoul wall-clock value; the service normalizes it
to an absolute UTC trigger while preserving the original local value.

```text
POST /v1/scout/schedules
  -> SQLite pending record
  -> persistent DateTrigger (Once) or Asia/Seoul CronTrigger (recurring)
  -> at due time: atomic pending -> running claim
  -> POST http://127.0.0.1:8091/v1/scout/runs
  -> copy authoritative Scout result metadata
  -> succeeded or failed audit record
```

Endpoints:

- `POST /v1/scout/schedules` creates a Once, Daily, Weekly, or Monthly schedule.
- `GET /v1/scout/schedules` lists pending and terminal audit history.
- `DELETE /v1/scout/schedules/{schedule_id}` cancels a pending schedule without
  deleting it.

Existing one-time payloads remain valid and default to `recurrence: "once"`.
Recurring payloads omit `run_at`, provide `schedule_time`, and add
`day_of_week` for Weekly or `day_of_month` for Monthly. All recurrence rules use
Asia/Seoul wall-clock time. Monthly day 29, 30, or 31 follows APScheduler cron
semantics and skips a month that does not contain that day.

Copy `.env.example` settings into the runtime environment, start Scout first,
then start this API:

```bash
uv run uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8092
```

Example creation request (use a future Seoul local time):

```bash
curl -X POST http://127.0.0.1:8092/v1/scout/schedules \
  -H 'Content-Type: application/json' \
  -d '{
    "topic": "고독사 예방 AI IoT 서비스 최근 동향",
    "keywords": ["고독사 예방", "AI 돌봄", "IoT 모니터링"],
    "recurrence": "once",
    "run_at": "2026-08-29T09:00:00",
    "timezone": "Asia/Seoul"
  }'
```

Example recurring request:

```bash
curl -X POST http://127.0.0.1:8092/v1/scout/schedules \
  -H 'Content-Type: application/json' \
  -d '{
    "topic": "고독사 예방 AI IoT 서비스 최근 동향",
    "keywords": ["AI 돌봄"],
    "recurrence": "weekly",
    "schedule_time": "09:00:00",
    "day_of_week": "monday",
    "timezone": "Asia/Seoul"
  }'
```

After each recurring execution, the row returns to `pending`, advances
`run_at`/`trigger_at` to its next occurrence, and keeps the latest Scout result
or safe error metadata. Cancelling that pending row removes the CronTrigger and
retains the audit record. The existing single-result schema does not retain a
separate result row for every occurrence.

The default Scout timeout is 180 seconds, execution concurrency is one, and
the misfire grace period is 300 seconds. Exactly one API process may own the
persistent scheduler. A validated single-worker systemd template now lives at
`deploy/systemd/nexgent-scout-scheduler.service`. It is installed, enabled, and
functionally verified as `nexgent-scout-scheduler.service` on port 8092.
Inspect it with
`systemctl status nexgent-scout-scheduler.service --no-pager` and
`journalctl -u nexgent-scout-scheduler.service -b -n 100 --no-pager`. See
`SCHEDULING_POC.md` for recovery and failure semantics.

## Observability

Built-in telemetry exports to Cloud Trace, BigQuery, and Cloud Logging.

## A2A Inspector

This agent supports the [A2A Protocol](https://a2a-protocol.org/). Use the [A2A Inspector](https://github.com/a2aproject/a2a-inspector) to test interoperability.
See the [A2A Inspector docs](https://github.com/a2aproject/a2a-inspector) for details.

# AX Project · Nexgent

**English** | [한국어](README.ko.md)

AX Project is Nextor.ai's workspace for applying AI and AI agents to existing products and business operations. **Nexgent**, the main application in this repository, brings conversational assistants, knowledge retrieval, research, care-service reporting, and file management into an authenticated operator interface.

The repository also contains project requirements, architecture/design material, and a separate scheduling prototype. Some capabilities integrate with the **Ansimk (안심지키미)** smart-care service and require access to its existing infrastructure.

## Contents

- [Capabilities](#capabilities)
- [Architecture](#architecture)
- [Repository layout](#repository-layout)
- [Prerequisites](#prerequisites)
- [Development setup](#development-setup)
- [Configuration reference](#configuration-reference)
- [Production and operations](#production-and-operations)
- [Development and testing](#development-and-testing)
- [Troubleshooting](#troubleshooting)
- [Further documentation](#further-documentation)

## Capabilities

| Area | Implemented functionality |
| --- | --- |
| AX Chat | Streaming conversations, persistent chat history, document/image attachments, and OpenAI-compatible model integration. |
| Knowledge / RAG | Document and text ingestion, vector retrieval backed by PostgreSQL/pgvector, and a retrieval-assisted chat workflow. The RAG API runs separately. |
| Weekly Reporter | Ansimk care-recipient reports, background bulk processing, job progress, ZIP exports, database storage, and scheduled execution. |
| Scout | Google ADK research agent that searches public web sources and saves Markdown reports and execution artifacts. Scheduling uses a separate service. |
| Files | Nextcloud integration and private per-user storage with folders, uploads, downloads, previews, trash, and restore. |
| Sumin | Slack upload archiving to Nextcloud and channel-scoped file discovery through bot mentions. |
| Accounts | Sign-in, account settings, administrator-managed access, and English/Korean interface text. |
| Notifications | Durable Slack notification jobs and a separate delivery worker. |

Signed-in members can use Chat, files, account settings, and the agent catalog. Knowledge and agent workspaces—including Scout and Weekly Reporter—require administrator access. See the [access policy](nexgent/docs/08-implementation/admin-only-knowledge-agent-pages.md).

## Architecture

```mermaid
flowchart TD
    UI[React / TypeScript UI] --> Gateway[FastAPI backend: authentication and gateway]
    Gateway --> DB[(PostgreSQL: accounts and application data)]
    Gateway --> ChatWorker[Durable chat worker]
    ChatWorker --> Agents[LangGraph Agent Server]
    Gateway --> Files[Nextcloud]
    Gateway --> Scout[Google ADK Scout]
    Gateway --> Reports[Weekly-report API and workers]
    Gateway --> RAG[Separate RAG API]
    Gateway --> Scheduler[Separate Scout scheduler]
    Agents --> Model[OpenAI-compatible model endpoint]
    Agents --> RAG
    Scout --> Model
    RAG --> VectorDB[(PostgreSQL / pgvector)]
    Reports --> CareDB[(Ansimk source and report databases)]
    Slack[Slack] <--> Sumin[Sumin listener and worker]
    Sumin --> Files
```

The browser uses same-origin backend routes. The backend enforces authentication and proxies to fixed upstream services. Chat and notification workers run separately from the API. The main Compose files keep the Agent Server private; its current `langgraph dev` runtime uses in-memory state and has no native authentication. Durable product chat history is stored by the backend, independently of that runtime.

The frontend uses React 18, TypeScript, and Vite. A Tauri 2/Rust desktop shell is also present; the Docker frontend runs the browser application. Python services use FastAPI, LangGraph, or Google ADK according to their role.

## Repository layout

```text
ax-project/
├── nexgent/                         Main application
│   ├── frontend/                    React web UI and Tauri desktop shell
│   ├── backend/                     API, authentication, migrations, workers
│   ├── agents/                      LangGraph services and business workflows
│   │   ├── apps/                    APIs, schedulers, and workers
│   │   ├── workflows/               Chat, RAG, reporting, Sumin, and other workflows
│   │   ├── packages/                Shared contracts, tools, integrations, runtime
│   │   └── tests/                   Unit, contract, integration, and evaluation tests
│   ├── adk_agents/                  Scout and experimental ADK agents
│   ├── RAG/                         Retrieval API, ingestion, pgvector, evaluation
│   ├── docs/                        Product, architecture, and implementation records
│   ├── compose.yaml                 Development stack
│   └── compose.prod.yaml            Stable-server stack
├── scheduling-agent-poc/            Separate scheduling service/prototype
├── requirement_analysis/            Initial requirements and implementation phases
├── project안심지키미/                  Care-service workflow material
└── *.md, *.pdf, *.png               Project notes, designs, and reference material
```

## Prerequisites

For the container workflow:

- Docker Engine and a recent Docker Compose v2 supporting `include` and optional `env_file` entries. The included Sumin deployment uses Linux host networking.
- Python 3 for the signing-key setup helper.
- A reachable PostgreSQL database and the external Docker network `nexgent-rag_default`. The included RAG database stack can provide both for local development.
- A reachable OpenAI-compatible model endpoint and its credentials.
- An Ansimk source database for the weekly-report source service, which is a dependency of the supplied application stack.
- Nextcloud credentials for file features; Slack and additional database credentials for Sumin and notification/report integrations.

For development outside containers, use Node.js 22 with npm (matching the frontend Docker image), Python 3.11+ for backend/LangGraph code, and `uv`. Scout's container uses Python 3.12. Desktop builds also need Rust and native Tauri dependencies; see the [frontend guide](nexgent/frontend/README.md).

This is an integration application: copying example files alone does not provide working external services or credentials.

## Development setup

Run the following commands from `nexgent/`, unless a step says otherwise:

```bash
cd nexgent
```

### 1. Create local configuration files

These commands preserve any files that already exist:

```bash
test -f backend/dev.env || cp backend/example.env backend/dev.env
test -f agents/.env || cp agents/.env.example agents/.env
test -f adk_agents/ansimk_scout_agent/.env || cp adk_agents/ansimk_scout_agent/.env.example adk_agents/ansimk_scout_agent/.env
python3 backend/setup_env.py
```

Edit the files before starting services:

- In `backend/dev.env`, set `NEXGENT_DATABASE_URL`, `NEXGENT_PUBLIC_URL`, and the `NC_*` Nextcloud values. For local HTTP, set `NEXGENT_ALLOW_INSECURE_HTTP=true`. The public URL must exactly match the browser origin, including its port.
- In `agents/.env`, set the model URL, model name, and API key, plus `ANSIMK_DATABASE_DSN` for the report source. Report persistence additionally needs `WEEKLY_REPORT_STORAGE_DATABASE_DSN`.
- In Scout's `.env`, set `OPENAI_API_BASE`, `OPENAI_API_KEY`, and `SCOUT_MODEL`. Use an endpoint reachable from the container; `127.0.0.1` inside a container refers to that container. Host-managed Scout environment files in `/etc/nexgent/` take precedence when present.

Keep populated environment files private. Use the checked-in examples as configuration references.

### 2. Prepare PostgreSQL

If the established database/network is already available, use it. For a new local database, prepare the included stack:

```bash
test -f RAG/.env || cp RAG/.env.example RAG/.env
# Edit RAG/.env and set RAG_POSTGRES_PASSWORD before continuing.
docker compose -f RAG/compose.yaml up -d
docker compose -f RAG/compose.yaml ps
```

This creates `nexgent-rag_default` and the pgvector PostgreSQL service. Its default database name is **`nextgent`** (including the `t`). From application containers, the established database endpoint is `nexgent-rag-postgres-1:5432`; from the host it is `127.0.0.1:5433`.

Set `NEXGENT_DATABASE_URL` to a valid SQLAlchemy URL using the appropriate database role, for example:

```dotenv
NEXGENT_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@nexgent-rag-postgres-1:5432/nextgent
NEXGENT_PUBLIC_URL=http://localhost:5173
NEXGENT_ALLOW_INSECURE_HTTP=true
```

Replace placeholders and URL-encode special characters in credentials. The backend runs Alembic migrations at startup; its database role must have the necessary schema permissions. This database setup does **not** populate the Ansimk source database or start the RAG API.

### 3. Start the application

To start the UI and its dependencies, chat processing, notifications, and report processing without starting Sumin:

```bash
docker compose up --build -d frontend chat-worker notification-worker weekly-report-worker
docker compose ps
curl --fail http://localhost:8000/health
```

For the complete development stack, first configure Sumin's `AGENT_DATABASE_DSN`, Slack bot/app tokens, and Nextcloud settings in `agents/.env`, then run:

```bash
docker compose up --build -d
```

The complete command also starts `sumin-migrate`, `sumin-events`, and `sumin-worker`. Missing Sumin credentials cause those services to fail; see the [Sumin setup guide](nexgent/agents/workflows/sumin/README.md).

### 4. Create the first administrator

After the backend is healthy, run this once for a database that has no initial administrator:

```bash
docker compose exec backend python -m app.identity.admin create-admin --username admin --name "Administrator"
```

Follow the password prompt, open <http://localhost:5173>, and sign in. Manage accounts and access in **Settings**. There is no bundled default password.

### 5. Enable separate services as needed

- **Knowledge / RAG chat:** start the separate RAG API and configure `AX_RAG_SERVER_URL` for the backend and `RAG_SERVER_BASE_URL` for the Agent Server. See the [RAG service guide](nexgent/RAG/docs/rag-server.md).
- **Scout schedules:** start the separate scheduling API on its configured address (default host port `8092`). See the [scheduler guide](scheduling-agent-poc/scheduling-agent/README.md).
- **Slack notifications:** configure the backend's `NEXGENT_SLACK_*` settings. See the [notification guide](nexgent/docs/08-implementation/slack-notification-service.md).

## Configuration reference

| File / scope | Main settings | Purpose |
| --- | --- | --- |
| `backend/dev.env` or `backend/prod.env` | `NEXGENT_DATABASE_URL`, `NEXGENT_PUBLIC_URL`, `NEXGENT_AUTH_SIGNING_KEY` | Application database, browser origin, session signing. |
| Backend environment | `NC_URL`, `NC_USER`, `NC_PASS`, `NC_CA_BUNDLE` | Nextcloud access and optional private CA trust. |
| Backend environment | `AX_AGENT_SERVER_URL`, `AX_RAG_SERVER_URL`, `AX_SCOUT_URL`, `AX_SCOUT_SCHEDULER_URL` | Private upstream addresses; Compose supplies several of these. |
| `agents/.env` | `URL` / `OPENAI_BASE_URL`, `MODEL` / `OPENAI_MODEL`, `OPENAI_API_KEY` | LangGraph model integration. |
| `agents/.env` | `ANSIMK_DATABASE_DSN`, `WEEKLY_REPORT_STORAGE_DATABASE_DSN` | Report source and report writer connections. |
| `agents/.env` | `AGENT_DATABASE_DSN`, `SUMIN_*` | Sumin database, Slack, and Nextcloud integration. |
| Scout `.env` | `OPENAI_API_BASE`, `OPENAI_API_KEY`, `SCOUT_MODEL` | Separate Scout model configuration. |
| `RAG/.env` | `RAG_POSTGRES_*` | Retrieval database connection. |
| Shell or `nexgent/.env` | `FRONTEND_PORT`, `BACKEND_PORT`, `PROD_FRONTEND_PORT`, `PROD_BACKEND_PORT` | Compose host-port overrides. |
| Shell or `nexgent/.env` | `SEARXNG_SECRET`, `WEEKLY_REPORT_JOB_PASSWORD` | Compose-interpolated service secrets; replace development defaults for deployment. |

Compose interpolation and container `env_file` loading are distinct. For values referenced as `${...}` in the main Compose files, use the shell or `nexgent/.env`; placing them only in `agents/.env` may not override an explicit Compose `environment` value. Consult [backend/example.env](nexgent/backend/example.env) and [agents/.env.example](nexgent/agents/.env.example) for the complete settings.

## Production and operations

| Environment | Compose file | Project | Frontend | Backend health |
| --- | --- | --- | --- | --- |
| Development | `compose.yaml` | `nexgent` | `http://localhost:5173` | `http://localhost:8000/health` |
| Stable server | `compose.prod.yaml` | `nexgent-prod` | `http://localhost:5174` | `http://localhost:8001/health` |

Backend host ports bind to loopback. For another device, use the Docker host's frontend address and configure the matching public origin. The stable-server frontend serves built assets through Nginx; the backend runs without development source mounts/reload.

Prepare `backend/prod.env` from `backend/example.env`, then generate its signing key:

```bash
python3 backend/setup_env.py --env-file prod.env
```

Set the production database, public origin, and integration credentials. Use HTTPS for public deployment. Production shares `agents/.env` with development, so separate Compose projects do not automatically isolate external databases, Slack destinations, or Nextcloud storage.

The production stack enables the weekly-report scheduler by default and mounts additional environment files, including `agents/playground/weekly-reporter/.env`. Configure the [scheduled reporting pipeline](nexgent/agents/apps/weekly_report_scheduler/README.md) before starting it. Development scheduling is behind the `scheduled` profile. Check the [actual cron definition](nexgent/agents/apps/weekly_report_scheduler/crontab) and scheduler guide for timing and pipeline stages. Sumin is included in the development Compose file, but not in `compose.prod.yaml`.

After completing that configuration:

```bash
docker compose -f compose.prod.yaml up --build -d
docker compose -f compose.prod.yaml ps
docker compose -f compose.prod.yaml logs -f
```

Common development operations:

```bash
docker compose logs -f backend agent-server chat-worker
docker compose down
```

Use `-f compose.prod.yaml` for production operations. `down` retains named volumes; `down -v` deletes them. Back up the application databases and persistent files before destructive maintenance. The separate RAG stack has its own lifecycle.

## Development and testing

Run each block from the repository root in a separate terminal or return to the root first.

**Frontend**

```bash
cd nexgent/frontend
npm ci
npm test
npm run build
npm run dev
```

The local Vite server proxies to `http://127.0.0.1:8000` by default; set `NEXGENT_BACKEND_TARGET` if needed. Stop the Docker frontend or select a different port before starting another server on port `5173`.

**Backend**

```bash
cd nexgent/backend
uv sync --extra dev
uv run pytest
```

See the [backend guide](nexgent/backend/README.md) for native API/worker startup, migrations, and environment loading. Native processes need host-reachable addresses instead of Docker service names.

**LangGraph services**

```bash
cd nexgent/agents
uv sync --dev
uv run pytest tests/unit tests/contract
uv run ruff check apps workflows packages tests
```

Integration tests and evaluations have additional service, database, or model requirements. Review the relevant test configuration before running them. Scout and the scheduler maintain their own environments and test suites; follow their component READMEs.

Before contributing, read the applicable `AGENTS.md` instructions. Material Nexgent implementation/infrastructure changes require a dated document under `nexgent/docs/` and an entry in its documentation index.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `nexgent-rag_default` is missing | Start the configured `RAG/compose.yaml` database stack or restore the expected external network/database setup. |
| Backend exits during startup | Check database reachability, schema permissions, signing key, and migration logs. |
| Login or a write request is rejected | Confirm `NEXGENT_PUBLIC_URL` exactly matches the browser origin; check HTTP opt-in for local development and sign in again after changing authentication configuration. |
| Knowledge or an agent workspace returns 403 | Use an administrator account; these routes have server-enforced access restrictions. |
| Chat or an integration returns 502/503 | Check the target service, worker logs, model credentials, and container-reachable URLs. RAG and Scout scheduling run separately. |
| Sumin exits or restarts | Check `AGENT_DATABASE_DSN`, both Slack tokens, Nextcloud credentials, and the configured CA file path. |
| Frontend waits for dependencies | Inspect `docker compose ps` and logs for Scout, Agent Server, backend, and report services. The UI waits for their health checks. |
| Reports fail admission or export | Check the artifact volume and free disk space; the default minimum free-space setting is 10 GiB. |

## Further documentation

- [Nexgent operations overview](nexgent/README.md)
- [Product and implementation documentation index](nexgent/docs/README.md)
- [Agent workspace and architecture](nexgent/agents/README.md)
- [Scout research agent](nexgent/adk_agents/ansimk_scout_agent/README.md)
- [RAG documentation index](nexgent/RAG/docs/README.md)
- [Scheduling service](scheduling-agent-poc/scheduling-agent/README.md)
- [Initial requirement analysis](requirement_analysis/README.md)
- [Original AX project context](ax_project.md)

Historical design notes describe both implemented and proposed behavior. For deployment details, check the current Compose files, example environments, code, and topic-specific implementation records together.

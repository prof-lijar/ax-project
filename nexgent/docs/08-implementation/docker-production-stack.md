# Docker Production Server Stack

Date: 2026-09-03

Status: Implemented and configuration validated; live image and runtime
validation remains an operator step because Docker socket access was not
available in the implementation session.

## Deployment Meaning

For this project, `production` identifies the separate stable server used by a
designated group of people after a release is tested. `development` identifies
the separate server used for new feature work. The term does not imply that the
Agent Server is hosted by LangSmith or that this internal deployment is an
internet-facing enterprise topology.

Each server runs its own Compose project, containers, network, and volumes. The
current production server deliberately runs the same tested application-level
Agent Server implementation with a different published port; it does not share
a running process or Docker state with development.

## Update: Weekly Reporter Cron Ownership

Date: 2026-09-04

The stable-server stack now owns the active Weekly Reporter schedule through
the private `weekly-report-scheduler` service. BusyBox cron runs every Monday
at 03:00 `Asia/Seoul` and idempotently submits the previous completed week to
the private bulk control API. The service has no database, model, or public
network boundary.

Development and agent-only Compose files contain the same service behind the
opt-in `scheduled` profile. This prevents development and stable stacks from
independently generating the same reporting week against shared external
source, writer, and model systems.

## Update: Priority README Runbook

Date: 2026-09-03

The root `README.md` now presents the two-server definition immediately after
the project introduction. Its high-visibility runbook includes the purpose and
port matrix, credential setup and temporary reuse warning, exact
start/stop commands, optional same-host validation, environment-specific
overrides, production endpoints, and the current runtime boundary. Detailed
implementation and validation evidence remains in this document.

## Summary

Nexgent now has two independent root Compose projects:

| Environment | Compose file | Project name | Frontend | Backend | Agent Server |
| --- | --- | --- | ---: | ---: | ---: |
| Development | `compose.yaml` | `nexgent` | `5173` | `8000` | `192.168.0.18:2024` |
| Production server | `compose.prod.yaml` | `nexgent-prod` | `5174` | `8001` | `192.168.0.18:2025` |

The development configuration and its ports are unchanged. Different project
names give each stack its own network, containers, weekly-report database,
report artifacts, and transient chat-attachment volume. Only published host
ports need to differ; internal service ports remain stable inside each isolated
Compose network.

The production frontend is compiled during image construction and served by
Nginx on container port `8080`. Nginx preserves the browser's existing
same-origin `/agent-server` and `/weekly-report-bulk-api` paths, disables proxy
buffering for streamed responses, and falls back to `index.html` for direct SPA
route loads. The production backend uses the immutable code in its image and
the Dockerfile's non-reloading Uvicorn command. Production containers do not
bind-mount application source or frontend dependencies.

## Implemented Files

- `compose.prod.yaml` defines the isolated production-server project, images,
  services, health checks, restart policies, volumes, and production-specific
  host-port variables.
- `frontend/Dockerfile.prod` builds the TypeScript/Vite application and copies
  only compiled assets into the Nginx runtime image.
- `frontend/nginx/default.conf` serves the SPA and proxies private Agent Server
  and weekly-report bulk API requests within the Compose network.
- `README.md` documents development and production-server startup, endpoints,
  overrides, shutdown, credentials, and current safety boundaries.
- `docs/08-implementation/docker-development-stack.md` now points to this
  implemented production server instead of describing it as only future work.
- `agents/docs/ax-agents-architecture.md` records that the new profile does not
  change the approved Agent Server production architecture or release gates.

## Configuration Decisions

### Ports

Production defaults use unprivileged adjacent ports so the two projects can run
concurrently:

```text
Frontend:     5174 -> 8080
Backend:      8001 -> 8000
Agent Server: 192.168.0.18:2025 -> 2024
```

Override them without changing development:

```bash
PROD_FRONTEND_PORT=15174 \
PROD_BACKEND_PORT=18001 \
PROD_AGENT_SERVER_PORT=12025 \
PROD_AGENT_SERVER_BIND_IP=192.168.0.18 \
docker compose -f compose.prod.yaml up --build -d
```

`PROD_BACKEND_PORT` is also supplied to the Vite build so browser API discovery
and the published backend port remain aligned. `PROD_FRONTEND_PORT` configures
the backend's port-scoped CORS origin rule.

### Credentials and environment

As requested for this stage, production temporarily uses the same ignored
credential files as development:

```text
agents/.env
backend/dev.env
```

Secrets are injected at container runtime and are not copied into application
images. The job database and SearXNG settings also retain the current
environment variable names and development fallback values. Deployment-specific
credential files can replace them during the planned credential update.

The external host-managed RAG and Scout endpoints retain their current default
addresses. They may be set at frontend image build time with
`VITE_RAG_SERVER_BASE_URL` and `VITE_SCOUT_API_BASE_URL`.

## Operations

Start development in the foreground:

```bash
docker compose up --build
```

Start production in the background:

```bash
docker compose -f compose.prod.yaml up --build -d
```

Inspect production status and logs:

```bash
docker compose -f compose.prod.yaml ps
docker compose -f compose.prod.yaml logs -f
```

Stop each project independently:

```bash
docker compose down
docker compose -f compose.prod.yaml down
```

Do not add `--volumes` to routine shutdown commands; the production project
owns persistent weekly-report state in its named volumes.

## Validation

Completed on 2026-09-03:

```text
docker compose -f compose.yaml config -q       passed
docker compose -f compose.prod.yaml config -q  passed
production default port rendering              passed
production custom port rendering               passed
npm run build                                  passed
compiled frontend backend-port embedding       passed
git diff --check                               passed
```

The rendered default production ports are `5174`, `8001`, and `2025`; custom
values were also propagated to the published ports, frontend build argument,
and backend CORS setting.

An image build was attempted but the account could not access
`/var/run/docker.sock`. Retrying with `sudo` could not authenticate without an
interactive terminal. Complete the remaining image and runtime verification on
the Docker host:

```bash
sudo docker compose -f compose.prod.yaml up --build -d
curl --fail http://127.0.0.1:5174/
curl --fail http://127.0.0.1:8001/health
curl --fail http://192.168.0.18:2025/ok
sudo docker compose -f compose.prod.yaml ps
```

All services should report healthy before handoff to users.

## Current Boundaries and Follow-up

- The production server intentionally builds the existing tested
  `agents/apps/agent_server/Dockerfile.dev`. It runs its own in-memory,
  noop-auth `langgraph dev` process inside the independent `nexgent-prod`
  project; it does not share the development server's process or Docker state.
- In the broader architecture documentation, `production-grade Agent Server`
  refers to a separate future hardening milestone with durable PostgreSQL and
  Redis, authenticated ingress, TLS, backups, monitoring, and rollback. That is
  not what the operational `production server` label means in this two-server
  setup.
- Runtime secrets currently come from development-named local files and current
  fallback credentials, as requested. Moving the same values into dedicated
  production credential files is planned later.
- Reusing the same environment files also means both stacks intentionally
  address the same Nextcloud, model, RAG, Scout, source-database, and report
  writer systems for now. Ports and Compose-owned volumes are isolated, but
  those external data systems are not.
- The frontend image embeds backend, RAG, and Scout endpoint settings at build
  time. Changing those values requires rebuilding the frontend image.
- Docker serves the browser frontend only; it does not package or run the Tauri
  desktop shell.


## Weekly reporter migration configuration

Date: 2026-09-13

The production `compose.prod.yaml` now directly mounts `agents/.env` and
`agents/playground/weekly-reporter/.env` read-only into the scheduler. Named
volumes retain migration receipts and SSH known hosts, and the scheduler has a
30-second shutdown grace period. No additional migration Compose overlay is
needed. The Monday 01:00 Asia/Seoul pipeline waits for committed local reports
before running migration with the reporting week start date.

From the `agents` directory, update only the scheduler:

```bash
docker compose -f ../compose.prod.yaml up -d --build --no-deps weekly-report-scheduler
```

Production Compose validation and five deployment contract tests passed. The
container has not been rebuilt or deployed and live migration has not been
run; execute the command above to activate the change. See the scheduler
README in `agents/apps/weekly_report_scheduler/` for recovery instructions.

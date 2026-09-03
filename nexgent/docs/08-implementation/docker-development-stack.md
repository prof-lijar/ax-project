# Docker Development Stack

Date: 2026-08-03 (Agent Server added 2026-08-10)

Status: Implemented and runtime verified on the Docker host.

## Update: Frontend Dependency Synchronization

Date: 2026-08-10

The frontend image now includes a lockfile-aware entrypoint. Compose preserves
`/app/node_modules` in a named volume while bind-mounting frontend source, so an
existing volume could remain stale after `package-lock.json` added a dependency.
At container startup, the entrypoint compares the current lockfile hash with a
marker in the dependency volume and runs `npm ci` only when they differ. This
keeps Vite imports synchronized without deleting the volume or reinstalling
unchanged dependencies on every restart.

After pulling the entrypoint change, rebuild and recreate the frontend once:

```bash
docker compose up --build -d frontend
```

The first recreated start updates the existing dependency volume; subsequent
starts skip installation until the lockfile changes again.

## Summary

Nexgent now has a Docker Compose development stack that starts the FastAPI
backend and Vite browser frontend together. It reproduces these host commands
inside isolated containers:

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
npm run dev -- --host 0.0.0.0
```

The FastAPI service is the backend, the Vite service is the frontend, and the
license-free Agent Server runs the agents workspace's in-memory `langgraph dev`
runtime. The frontend's same-origin `/agent-server` proxy targets the Agent
Server by its Compose service name.

This is a development stack. It uses source bind mounts, polling file watchers,
and reload servers. It is not intended to be deployed directly as a production
stack.

## Service Layout

| Service | Container process | Host port | Container port | Health check |
| --- | --- | ---: | ---: | --- |
| `backend` | Uvicorn with reload | `8000` | `8000` | `GET /health` |
| `frontend` | Vite development server | `5173` | `5173` | `GET /` |
| `agent-server` | LangGraph dev server | `192.168.0.18:2024` | `2024` | `GET /ok` |

The frontend waits for both backend and Agent Server health checks before
starting. All services bind to `0.0.0.0` inside their containers so their
published host ports are reachable outside Docker. The Agent Server host port
is restricted to the host's `192.168.0.18` LAN interface.

## Implemented Files

- `compose.yaml`
  - Defines the three services, port publishing, health checks, live-reload
    mounts, startup dependency, and graceful shutdown timing.
  - Supports `FRONTEND_PORT` and `BACKEND_PORT` host-port overrides.
  - Keeps container dependencies isolated from host `node_modules` through a
    named volume.
- `agents/apps/agent_server/Dockerfile.dev`
  - Installs the locked agents workspace and starts `langgraph dev` without a
    LangSmith license, PostgreSQL, Redis, or the production gateway.
  - Binds `0.0.0.0:2024` inside Docker; Compose publishes it as
    `192.168.0.18:2024`.
- `backend/Dockerfile`
  - Uses the official Python 3.12 slim Bookworm base image.
  - Copies the executables from Astral's pinned, version-only `uv` image in a
    separate build stage. This avoids coupling the `uv` version to a derived
    Python/base-distribution tag that may not be published.
  - Installs dependencies from `uv.lock` with locked resolution.
  - Runs as the non-root `nexgent` user.
  - Includes LibreOffice Writer, Impress, and Calc so DOCX, PPTX, and XLSX
    previews retain their existing conversion behavior.
- `frontend/Dockerfile`
  - Uses Node.js 22 and installs dependencies with `npm ci`.
  - Runs the Vite server as the non-root `node` user.
  - Installs a lockfile-aware entrypoint that synchronizes the persistent
    dependency volume when frontend packages change.
- `frontend/docker-entrypoint.sh`
  - Compares the current package-lock hash with the installed-volume marker,
    runs `npm ci` only after dependency changes, and then starts the requested
    container command.
- `backend/.dockerignore` and `frontend/.dockerignore`
  - Exclude local environments, credentials, dependency directories, build
    output, Rust build artifacts, and caches from image build contexts.
- `README.md`
  - Documents Docker startup, shutdown, port overrides, dependency refreshes,
    credentials, and Docker socket troubleshooting.

## Application Changes Supporting Docker

### Backend health check

The backend now exposes:

```text
GET /health
```

It returns `{"status":"ok"}` without loading Nextcloud credentials or making
an external integration request. Compose uses this endpoint to determine when
the API process is ready.

### Configurable CORS

Hard-coded local development origins remain available outside Docker. The
backend also supports:

- `NEXGENT_CORS_ORIGINS`: comma-separated exact origins.
- `NEXGENT_CORS_ORIGIN_REGEX`: an explicit origin regular expression.
- `NEXGENT_CORS_FRONTEND_PORT`: generates a development origin rule for the
  Compose frontend port when no explicit regex is supplied.

Compose sets the frontend-port value automatically. The rule remains limited
to the configured frontend port and the backend continues to allow only `GET`
cross-origin methods.

### Browser backend discovery

The browser client now accepts `VITE_BACKEND_PORT`. Compose sets it from the
published backend port so custom host ports work without source edits.
`VITE_BACKEND_URL` remains the higher-priority full URL override.

## Local Environment

Nextcloud credentials are not copied into the backend image. Compose reads the
ignored `backend/dev.env` file at runtime.

Create it from the committed template:

```bash
cp backend/example.env backend/dev.env
```

Required values:

```text
NC_URL
NC_USER
NC_PASS
```

For a private certificate authority, mount the CA certificate into the backend
container and set `NC_CA_BUNDLE` to the path inside that container.

## Run Commands

Start and build all three services from the `nexgent/` directory:

```bash
docker compose up --build
```

On a host where the current account cannot access the Docker socket:

```bash
sudo docker compose up --build
```

After Docker reports that both services are running, check the frontend from
the LAN at:

```text
http://192.168.0.18:5173/
```

Vite reports its container network address in the logs, for example
`http://172.19.0.3:5173/`. That address is internal to Docker. LAN clients must
use the published Docker-host address `http://192.168.0.18:5173/`.

Local endpoints on the Docker host are:

```text
Frontend:         http://localhost:5173
Backend API docs: http://localhost:8000/docs
Backend health:   http://localhost:8000/health
Agent Server:     http://192.168.0.18:2024/ok
```

## Agent Server Compose Update Validation

The parent Compose configuration was rendered successfully with the agents
workspace as its build context, the Agent Server health check, the exact
`192.168.0.18:2024:2024` port mapping, and the frontend proxy target
`http://agent-server:2024`. A live image build and health request still require
Docker socket access on the host:

```bash
sudo docker compose up --build -d
curl http://192.168.0.18:2024/ok
```

Use different published ports:

```bash
FRONTEND_PORT=5174 BACKEND_PORT=8080 docker compose up --build
```

Stop the stack:

```bash
docker compose down
```

After frontend dependency changes, rebuild and recreate the frontend. The
entrypoint refreshes its dependency volume automatically:

```bash
docker compose up --build -d frontend
```

## Validation on 2026-08-10

The dependency entrypoint passed `sh -n`, the frontend's 15 tests and production
build passed, the Compose configuration rendered, and `git diff --check` passed.
Building the updated image could not be completed in this session because the
current account cannot access `/var/run/docker.sock`. Remaining verification:

```bash
sudo docker compose up --build -d frontend
sudo docker compose logs frontend
```

The frontend log should report that dependencies are being synchronized once,
then show the Vite ready message without a `react-markdown` resolution error.

## Validation on 2026-08-03

Completed successfully:

```text
Backend tests:                 17 passed
Frontend TypeScript/Vite build: passed
Default Compose validation:    passed
Custom-port Compose validation: passed
Custom CORS override parsing:  passed
Corrected uv manifest lookup:  passed (AMD64 and ARM64)
Python base manifest lookup:    passed (AMD64 and ARM64)
Node base manifest lookup:      passed (AMD64 and ARM64)
Backend image build:            passed
Frontend image build:           passed
Backend health check:           passed (HTTP 200)
Frontend Vite startup:          passed
Git whitespace validation:     passed
```

### Host Docker run

The first interactive host build on 2026-08-03 reached Docker BuildKit but
failed before executing image layers because this backend base tag did not
exist:

```text
ghcr.io/astral-sh/uv:0.11.32-python3.12-bookworm-slim
```

The Dockerfile was then changed to use two explicit stages:

```dockerfile
FROM ghcr.io/astral-sh/uv:0.11.32 AS uv
FROM python:3.12-slim-bookworm
COPY --from=uv /uv /uvx /bin/
```

The same concurrent attempt also reported that frontend metadata could not be
loaded for `node:22-alpine`, but it did not provide a separate registry error
before the backend failure stopped the build. A subsequent registry-only lookup
confirmed that the Node tag exists for both AMD64 and ARM64, so no frontend
Dockerfile change was needed.

After the Dockerfile correction, the host build and startup completed
successfully on 2026-08-03. The relevant runtime evidence was:

```text
[+] up 4/4
Image nexgent-backend        Built
Image nexgent-frontend       Built
Container nexgent-backend-1  Recreated
Container nexgent-frontend-1 Recreated

backend-1  | Uvicorn running on http://0.0.0.0:8000
backend-1  | Application startup complete.
backend-1  | "GET /health HTTP/1.1" 200 OK
Container nexgent-backend-1 Healthy

frontend-1 | VITE v8.1.3 ready
frontend-1 | Local:   http://localhost:5173/
frontend-1 | Network: http://172.19.0.3:5173/
```

The Vite `Network` address above belongs to the Compose network. The published
frontend is checked from the LAN at:

```text
http://192.168.0.18:5173/
```

## Current Boundaries and Next Work

- Docker serves the browser version of the frontend; it does not run the Tauri
  desktop shell, which requires host display and native OS integration.
- The stack is optimized for local development, not production hardening.
- A separate [stable production-server stack](docker-production-stack.md) now uses
  built frontend assets, Nginx, immutable application containers, isolated
  volumes, and non-conflicting host ports. Explicit secret management,
  authenticated ingress, and deployment-specific TLS remain follow-up work.
- The Agent Server uses in-memory development persistence and noop
  authentication; it is restricted to the trusted LAN and is not a production
  deployment.

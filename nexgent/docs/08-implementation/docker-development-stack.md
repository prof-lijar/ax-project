# Docker Development Stack

Date: 2026-08-03

Status: Implemented and runtime verified on the Docker host.

## Summary

Nexgent now has a Docker Compose development stack that starts the FastAPI
backend and Vite browser frontend together. It reproduces these host commands
inside isolated containers:

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
npm run dev -- --host 0.0.0.0
```

The FastAPI service is the backend and the Vite service is the frontend. Agent
runtime services are intentionally outside the current scope and can be added
to the Compose project later.

This is a development stack. It uses source bind mounts, polling file watchers,
and reload servers. It is not intended to be deployed directly as a production
stack.

## Service Layout

| Service | Container process | Host port | Container port | Health check |
| --- | --- | ---: | ---: | --- |
| `backend` | Uvicorn with reload | `8000` | `8000` | `GET /health` |
| `frontend` | Vite development server | `5173` | `5173` | `GET /` |

The frontend waits for the backend health check before starting. Both services
bind to `0.0.0.0` inside their containers so their published host ports are
reachable outside Docker.

## Implemented Files

- `compose.yaml`
  - Defines the two services, port publishing, health checks, live-reload
    mounts, startup dependency, and graceful shutdown timing.
  - Supports `FRONTEND_PORT` and `BACKEND_PORT` host-port overrides.
  - Keeps container dependencies isolated from host `node_modules` through a
    named volume.
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

Start and build both services from the `nexgent/` directory:

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
```

Use different published ports:

```bash
FRONTEND_PORT=5174 BACKEND_PORT=8080 docker compose up --build
```

Stop the stack:

```bash
docker compose down
```

After frontend dependency changes, rebuild the image and refresh its dependency
volume:

```bash
docker compose build frontend
docker compose run --rm --no-deps frontend npm ci
```

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
- A future production design should use built frontend assets, a production
  HTTP server, immutable application containers, a reverse proxy or ingress,
  explicit secret management, and deployment-specific TLS.
- Agent services can later join the same Compose project with independent
  images, health checks, networks, and dependency rules.

# Nexgent

Nexgent consists of a FastAPI backend, a Vite web frontend, and a license-free
LangGraph development Agent Server.

## Docker Environments — Start Here

> **Important:** Development and production use different Compose projects and
> host ports. Use `compose.yaml` for development and `compose.prod.yaml` for the
> production server.

In this repository, **production means the separate stable server that runs
tested releases for a designated group of users**. Development is the separate
server where new features are built and tested. “Production” here does not mean
deployment on LangSmith.

| Server | Purpose | Compose file | Project | Frontend | Backend | Agent Server |
| --- | --- | --- | --- | ---: | ---: | ---: |
| Development | New feature development | `compose.yaml` | `nexgent` | `5173` | `8000` | `192.168.0.18:2024` |
| Production | Tested release for the user group | `compose.prod.yaml` | `nexgent-prod` | `5174` | `8001` | `192.168.0.18:2025` |

The intended deployment is one stack on each server. The different project
names, ports, and Docker-managed volumes also keep them isolated if both are
temporarily run on one host for validation. Internal container ports remain
unchanged.

### Required local credentials

Create the ignored backend environment file and add the Nextcloud values:

```bash
cp backend/example.env backend/dev.env
```

Create the ignored Agent Server environment file and add `OPENAI_API_KEY`:

```bash
cp agents/.env.example agents/.env
```

For now, **both environments intentionally use these same credential files**:

```text
backend/dev.env
agents/.env
```

This also means both stacks connect to the same configured external Nextcloud,
model, RAG, Scout, source-database, and report-writer systems. Their Docker
volumes and ports are separate, but those external systems are not.

### Development

Start development with live source reload:

```bash
docker compose up --build
```

Development endpoints:

- Frontend: <http://localhost:5173>
- Backend API docs: <http://localhost:8000/docs>
- Backend health: <http://localhost:8000/health>
- Agent Server: <http://192.168.0.18:2024>
- Agent Server API docs: <http://192.168.0.18:2024/docs>

Stop development:

```bash
docker compose down
```

### Production server

On the stable production server, start the tested release in the background:

```bash
docker compose -f compose.prod.yaml up --build -d
```

Production-server endpoints:

- Frontend: <http://localhost:5174>
- Backend API docs: <http://localhost:8001/docs>
- Backend health: <http://localhost:8001/health>
- Agent Server: <http://192.168.0.18:2025>
- Agent Server API docs: <http://192.168.0.18:2025/docs>

Check status and logs:

```bash
docker compose -f compose.prod.yaml ps
docker compose -f compose.prod.yaml logs -f
```

Stop the production server stack without deleting its volumes:

```bash
docker compose -f compose.prod.yaml down
```

The production server builds static frontend assets and serves them through
Nginx. The backend runs from immutable image code without source mounts or
auto-reload. See the [production-server implementation and operations
record](docs/08-implementation/docker-production-stack.md) for architecture,
validation, and operating details.

### Run both environments

If both stacks must be validated temporarily on one host, start them in the
background with their separate Compose files:

```bash
docker compose up --build -d
docker compose -f compose.prod.yaml up --build -d
```

They remain independently manageable because their project names and published
ports differ.

### Port overrides

Development keeps the current defaults. Its frontend and backend ports can be
overridden with the existing variables:

```bash
FRONTEND_PORT=55173 BACKEND_PORT=58000 docker compose up --build
```

Use only the `PROD_` variables for the production server:

```bash
PROD_FRONTEND_PORT=15174 \
PROD_BACKEND_PORT=18001 \
PROD_AGENT_SERVER_PORT=12025 \
PROD_AGENT_SERVER_BIND_IP=192.168.0.18 \
docker compose -f compose.prod.yaml up --build -d
```

Changing `PROD_BACKEND_PORT`, `VITE_RAG_SERVER_BASE_URL`, or
`VITE_SCOUT_API_BASE_URL` requires rebuilding the production frontend because
Vite embeds those browser settings at image-build time.

### Development rebuild notes

Development source directories are bind-mounted, so Python and frontend source
changes reload automatically. Rebuild the backend after changing its lockfile
or Dockerfile:

```bash
docker compose build backend
```

Frontend dependencies live in a named volume so host `node_modules` does not
leak into Linux containers. Refresh that volume after changing
`package-lock.json`:

```bash
docker compose build frontend
docker compose run --rm --no-deps frontend npm ci
```

Vite may print a container-network URL such as `http://172.19.0.3:5173/`.
Other LAN devices must use the published Docker-host address, for example
`http://192.168.0.18:5173/`.

If the current account cannot access the Docker socket, use the same commands
with `sudo` or configure Docker access for that account.

The Docker frontend is the browser UI. It does not run the Tauri desktop shell,
which requires host display and native OS integration.

## Current Agent Server Boundary

The production server intentionally runs the same tested application-level
Agent Server implementation as development, but in its own Compose project and
container. It currently uses the in-memory, noop-auth `langgraph dev` runtime
and the same credential values, as requested. This does not mean the production
and development servers share a running Agent Server process or Docker state.

Keep both servers on the approved internal network. Authentication, TLS,
durable Agent Server storage, deployment-managed secrets, backups, and
monitoring can be introduced later if the stable server's access or durability
requirements expand.

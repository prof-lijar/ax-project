# Nexgent

Nexgent consists of a FastAPI backend, a Vite web frontend, and a license-free
LangGraph development Agent Server.

## Login and access administration

Login is part of the main app. Use the normal development or production Compose
file; there is no separate account stack or authentication mode. Users sign in
before opening features, and administrators manage access under **Settings**.

Configure `NEXGENT_DATABASE_URL`, `NEXGENT_PUBLIC_URL` and the login signing key in
`backend/dev.env` (development) or `backend/prod.env` (production). Account storage
uses your existing PostgreSQL database and the `auth` schema. The backend runs
migrations before starting; it does not provision an account database.

See [Unified App Authentication](docs/08-implementation/unified-app-authentication.md)
for setup, initial admin creation, extension points and verification, and the
[detailed database schema](docs/05-data/identity-access-database-plan.md) for all eight tables.

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
| Development | New feature development | `compose.yaml` | `nexgent` | `5173` | `8000` | Internal only |
| Production | Tested release for the user group | `compose.prod.yaml` | `nexgent-prod` | `5174` | `8001` | Internal only |

The intended deployment is one stack on each server. The different project
names, ports, and Docker-managed volumes also keep them isolated if both are
temporarily run on one host for validation. Internal container ports remain
unchanged.

### Required local credentials

For a fresh installation, copy `backend/example.env` to `backend/dev.env`
(or `backend/prod.env` for production), then fill in the existing database URL,
the exact browser origin, and Nextcloud settings. Do not overwrite an existing
environment file. Generate a missing login signing key:

```bash
python3 backend/setup_env.py
# Production:
python3 backend/setup_env.py --env-file prod.env
```

Production normally uses a different browser origin (local default port 5174).
Both Compose backends join the existing `nexgent-rag_default` database network;
the PostgreSQL container must already be running. Use
`nexgent-rag-postgres-1:5432` as the database endpoint inside Docker. See
[Backend PostgreSQL Docker Network](docs/08-implementation/backend-postgresql-docker-network.md)
for configuration and verification.

For HTTP development, explicitly set `NEXGENT_ALLOW_INSECURE_HTTP=true`;
otherwise use HTTPS. Set `NEXGENT_PUBLIC_URL` to the actual address used in your
browser, including the port.

Create the ignored Agent Server environment file and add `OPENAI_API_KEY` if
that file does not already exist:

```bash
cp agents/.env.example agents/.env
```

Backend environments have separate files; the existing agent services still use
`agents/.env`. External integration destinations may still be shared between
development and production, depending on those files.

The stable production stack is the default owner of the Weekly Reporter cron
schedule and submits the previous completed week every Monday at 03:00 KST.
The development scheduler is behind the optional `scheduled` Compose profile
to prevent duplicate model work and report writes while both environments are
running.

### Development

Start development with live source reload:

```bash
docker compose up --build
```

Development endpoints:

- Frontend: <http://localhost:5173>
- Backend health: <http://localhost:8000/health>
- Agent Server: internal Docker network; the frontend uses the authenticated backend gateway.

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
- Backend health: <http://localhost:8001/health>
- Agent Server: internal Docker network; the frontend uses the authenticated backend gateway.

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
docker compose -f compose.prod.yaml up --build -d
```

When changing the browser address/port, update `NEXGENT_PUBLIC_URL` in the
corresponding backend environment file. Browser API calls use the same origin;
upstream addresses are server-side settings and require a backend restart.

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

The Agent Server has no published host port and is reached through the
authenticated Nexgent backend. Keep private integration endpoints isolated from
untrusted clients. Durable Agent Server storage and per-resource permissions
remain future work; the current feature access policy is company-wide login.

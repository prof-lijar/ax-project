# Scout ADK Compose integration

Date: 2026-09-07 (Asia/Seoul)

## Implemented behavior

Both `compose.yaml` and `compose.prod.yaml` start the Scout ADK API as a default
`scout` service. The frontend waits for its HTTP liveness check. The image uses
Python 3.12 and frozen uv dependencies, runs as UID/GID 10001, and excludes
.env files, tests, reports, and host virtualenvs from the build context.

Browser requests use the relative `/scout-api` URL. Vite (development) and nginx
(production) strip this prefix and forward to `http://scout:8091` on the Compose
network with a 240-second upstream timeout. This removes the browser's dependency
on a hard-coded host address and cross-origin permission for Docker usage.
No Scout host port is published.

## Configuration and startup

Configure `adk_agents/ansimk_scout_agent/.env` using its .env.example. Required
model variables are OPENAI_API_BASE, OPENAI_API_KEY, and SCOUT_MODEL; optional
Slack variables are SCOUT_SLACK_BOT_TOKEN and SCOUT_SLACK_CHANNEL_ID.

For compatibility on this host, Compose also reads the optional
`/etc/nexgent/internal-openai.env` and `/etc/nexgent/nexgent-scout.env` files.
The project .env is read first; host-managed files override it when present.
This preserves the configured model if a copied .env.example has blank keys or
placeholder model values. Slack settings still come from .env unless also set
in a host-managed file. None are copied into
the image. SCOUT_OUTPUT_ROOT is set to /app/var in the container.
A model on the host must use a container-reachable address, such as
`http://host.docker.internal:8001/v1`, not localhost.
Do not replace a working remote model endpoint.

From the nexgent directory:

```bash
docker compose up -d --build
docker compose ps scout
curl -fsS http://localhost:5173/scout-api/health/live
curl -fsS http://localhost:5173/scout-api/health/ready
```

Use sudo for Docker commands if required by the host. If the rest of the
development stack is already running, update just these services:

```bash
docker compose up -d --build scout frontend
```

Production:

```bash
docker compose -f compose.prod.yaml up -d --build
curl -fsS http://localhost:5174/scout-api/health/ready
```

Adjust the frontend port if overridden. Liveness permits frontend startup even
without model credentials; readiness returns 503 until those credentials are
configured. Recreate the Scout container after editing its environment file.

## Persistence and existing host services

The named `scout-reports` volume persists reports and execution logs across
container recreation. Development and production use separate Compose-project
volumes. Do not use `docker compose down -v` when reports must be retained.
Existing host reports remain intact and are not automatically migrated.

The existing systemd Scout service and scheduler were not stopped or changed.
The scheduler lives outside adk_agents in a separate project and still calls
the host Scout API. Scheduled execution is therefore not migrated by this
change; host Scout still needs its own restart to load the earlier Slack code.
The test-agent directory is a development prototype and is not part of default
product startup. This integration containerizes the product Scout API.

## Validation and limitations

- Both Compose configurations pass `docker compose config --quiet` using
  Docker Compose v5.2.0, without emitting resolved credentials.
- Frontend `npm run build` passed; `npm audit --audit-level=moderate` found
  zero vulnerabilities.
- `git diff --check` passed.
- The required Rust check failed because cached Tauri build metadata references
  a missing workflow-helper permission file outside this project. Rust code
  was not changed. Remaining command:
  `cargo check --manifest-path frontend/src-tauri/Cargo.toml`.
- The Scout image build could not run: this account cannot access
  /var/run/docker.sock and sudo requires interactive authentication.
  No container startup, nginx runtime, or browser research run was verified.
  Remaining commands are the startup/health commands above, followed by one
  research run through the UI (which posts to Slack if configured).

## Update: 2026-09-07 — missing model key / HTTP 503

The development proxy returned HTTP 503 with "Scout service is not configured."
The resolved Compose configuration had an empty OPENAI_API_KEY: the local .env
overrode the populated host-managed model environment. Both Compose files now
load local values first, then the host-managed files. No credential values or
model selections were changed. Validation inspects only presence/readiness,
never prints resolved secrets.

Recreate the container to reload its environment (restart alone is insufficient):

```bash
sudo docker compose up -d --no-deps --force-recreate scout
curl -fsS http://localhost:5173/scout-api/health/ready
```

For production, add `-f compose.prod.yaml` and use frontend port 5174.

Historical standalone deployment documentation is superseded only for Docker
Run Now traffic. Model readiness checks configuration presence, not a live
model request.

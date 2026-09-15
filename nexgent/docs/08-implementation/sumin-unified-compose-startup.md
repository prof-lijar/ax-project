# Sumin unified Compose startup

Date: 2026-09-15

The default `nexgent/compose.yaml` includes `agents/compose.sumin.yaml`, so the
standard root command starts Sumin alongside the existing application services:

```bash
sudo docker compose up --build -d
```

No extra Compose filename, profile, environment flag, or second startup command
is required. The included services belong to the root `nexgent` Compose project:

- `sumin-migrate`: idempotent schema setup; exits successfully before consumers start.
- `sumin-events`: outbound Slack Socket Mode connection and durable event enqueue.
- `sumin-worker`: leased archive/search tasks and channel-scoped Slack replies.

Sumin definitions remain under `agents/` to keep ownership in one place.
Compose resolves build context and service env-file paths relative to that
included file. Its explicit include env file also reads `agents/.env` for
Nextcloud CA mount interpolation. The shared `AGENT_DATABASE_DSN` and all
`SUMIN_*` settings remain in `agents/.env`; no credentials are copied into
root Compose or root environment files.

The existing Linux host networking reaches PostgreSQL published at
127.0.0.1:5433. Sumin exposes no inbound ports. Nextcloud CA mounting and
certificate verification remain in place. The other root services retain their
existing definitions and dependencies. Docker Compose 2.20 or newer is required
for `include`; the installed version is 5.2.0.

From `nexgent/`, inspect Sumin with the same project command:

```bash
sudo docker compose ps -a sumin-migrate sumin-events sumin-worker
sudo docker compose logs --tail=100 sumin-migrate sumin-events sumin-worker
```

If an older `ax-sumin` standalone project was actually started, stop it once
before starting the unified stack to avoid duplicate listeners:

```bash
sudo docker compose -p ax-sumin -f agents/compose.sumin.yaml down
```

This migration cleanup is not required when the standalone stack never ran.
Normal root `docker compose down` now also stops Sumin. The separately selected
production Compose file is not changed by this default-stack integration.

Validation: root Compose rendering confirmed all three unprofiled Sumin
services, the root project name, the `agents` build/env paths, and migration
completion dependencies. All 10 focused include-contract and Socket Mode
regression tests passed; Ruff and whitespace checks passed. Runtime build/start remains operator-owned because
this assistant account cannot access the Docker daemon. Slack app token/scopes
and Nextcloud certificate setup remain required for successful uploads; unified
startup does not bypass those checks.

See [Sumin setup](../../agents/workflows/sumin/README.md) for configuration and
[Docker include semantics](https://docs.docker.com/reference/compose-file/include/).

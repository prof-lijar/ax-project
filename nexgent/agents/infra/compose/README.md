# Self-hosted runtime

This Compose file is an integration and VM deployment baseline. Copy
`agents/.env.example` to `agents/.env` if creating a fresh workspace, then
configure the image, database and runtime keys in that unified file. From
`agents/`, build the runtime images and run:

```bash
docker compose --env-file .env -f infra/compose/docker-compose.yml up -d
```

Service `env_file` paths also point to `agents/.env`; no infra-local env is read.

The topology also runs an internal SearXNG service for reusable web discovery.
Set `SEARXNG_SECRET` to a random service secret. SearXNG has no published host
port, exposes JSON only to the Compose network, and requires no upstream search
API key. The Agent Server waits for it to become healthy.

Do not use the example password or expose Agent Server directly to the public
network. Production deployments need TLS termination, authenticated gateway
requests, backups, monitoring, and a migration/rollback procedure.

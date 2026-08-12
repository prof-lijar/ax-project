# Self-hosted runtime

This Compose file is an integration and VM deployment baseline. Copy
`.env.example` to `.env`, provide deployment secrets through a secret manager,
build the Agent Server and gateway images, then run `docker compose up`.

The topology also runs an internal SearXNG service for reusable web discovery.
Set `SEARXNG_SECRET` to a random service secret. SearXNG has no published host
port, exposes JSON only to the Compose network, and requires no upstream search
API key. The Agent Server waits for it to become healthy.

Do not use the example password or expose Agent Server directly to the public
network. Production deployments need TLS termination, authenticated gateway
requests, backups, monitoring, and a migration/rollback procedure.

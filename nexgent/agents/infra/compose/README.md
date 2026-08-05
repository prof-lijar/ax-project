# Self-hosted runtime

This Compose file is an integration and VM deployment baseline. Copy
`.env.example` to `.env`, provide deployment secrets through a secret manager,
build the Agent Server and gateway images, then run `docker compose up`.

Do not use the example password or expose Agent Server directly to the public
network. Production deployments need TLS termination, authenticated gateway
requests, backups, monitoring, and a migration/rollback procedure.

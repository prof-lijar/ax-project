# Backend PostgreSQL Docker Network

Date: 2026-09-21

## Failure and cause

The backend exited in `alembic upgrade head` with a PostgreSQL connection refusal
at `127.0.0.1:5433`. Both backend environment files used the host-side endpoint.
Inside the backend container, loopback refers to that container.

The supplied Docker inventory identifies the existing PostgreSQL container as
`nexgent-rag-postgres-1`, attached to `nexgent-rag_default`. Its internal port is
5432; its host publication is `127.0.0.1:5433`. A host-gateway alias does not make
that loopback-only host publication accessible from another container.

## Implementation

- Both root Compose files attach only the backend to the existing external
  `nexgent-rag_default` network through the Compose network key `database`.
- The backend retains its project `default` network for frontend and feature
  service communication.
- Local ignored `backend/dev.env` and `backend/prod.env` now use
  `nexgent-rag-postgres-1:5432` in `NEXGENT_DATABASE_URL`. Existing credentials,
  database name `nextgent`, and other URL components are preserved.
- Nexgent does not create or manage this database or network. The database's
  host port remains loopback-only. Authentication tables remain in `auth`.

The existing database stack must be running before Nexgent starts. If the database
is moved, update the external network name in both Compose files and the URL in
the applicable backend environment file. This deployment assumes the existing
container name remains stable.

## Apply and verify

From the project root, recreate the development backend with its new network and
environment, and start the frontend:

```bash
sudo docker compose up -d backend frontend
sudo docker compose logs --no-color --tail=100 backend
sudo docker compose ps backend frontend
curl --fail http://127.0.0.1:8000/health
```

The backend runs migrations before serving requests. Expect a healthy backend
and a health response of `{"status":"ok"}`. Existing images already contain the
entrypoint shown in the reported traceback; a rebuild is not needed for this
network/environment correction.

To apply the same configuration to production, rebuilding its older application
images as needed:

```bash
sudo docker compose -f compose.prod.yaml up -d --build backend frontend
sudo docker compose -f compose.prod.yaml logs --no-color --tail=100 backend
curl --fail http://127.0.0.1:8001/health
```

## Validation and remaining checks

Both Compose configurations resolve successfully. Assertions verified that the
backend belongs to both networks, only the backend joins the external database
network, and that the external network resolves to `nexgent-rag_default`.
Parsed database URLs were compared before and after: only host and port changed.
Both private environment files retain mode 0600. No secret values were printed.

Live container recreation, database connectivity, migrations, and application
health remain unverified: this agent cannot access the Docker socket, and sudo
requires an interactive password. Run the development commands above to finish
verification. Other startup errors, if any, will appear in the backend logs once
the network connection is corrected.

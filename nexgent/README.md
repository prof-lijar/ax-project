# Nexgent

Nexgent currently consists of a FastAPI backend, a Vite web frontend, and a
license-free LangGraph development Agent Server. The Docker development stack
starts all three services together.

## Run with Docker

Requirements:

- Docker Engine with Docker Compose
- Nextcloud credentials for the backend

Create the ignored local environment file and fill in your Nextcloud values:

```bash
cp backend/example.env backend/dev.env
```

Create the ignored Agent Server environment file and set `OPENAI_API_KEY`:

```bash
cp agents/.env.example agents/.env
```

Start the full development stack from this `nexgent/` directory:

```bash
docker compose up --build
```

If your account is not allowed to access the Docker socket, run the same
command with `sudo` or configure Docker access for that account first.

After Docker reports that both services are running, check the frontend from
the LAN at:

```text
http://192.168.0.18:5173/
```

Vite may print a `Network` URL such as `http://172.19.0.3:5173/` in the Docker
logs. That is the frontend container's internal network address. Use the
published host address `http://192.168.0.18:5173/` from other LAN devices.

Local endpoints on the Docker host are:

- Frontend: <http://localhost:5173>
- Backend API docs: <http://localhost:8000/docs>
- Backend health check: <http://localhost:8000/health>
- Agent Server: <http://192.168.0.18:2024>
- Agent Server API docs: <http://192.168.0.18:2024/docs>

Source directories are bind-mounted, so Python and frontend source changes
reload automatically. Rebuild the backend after changing its dependency lock
file or Dockerfile:

```bash
docker compose build backend
```

Frontend dependencies live in a named volume so the host's `node_modules` does
not leak into Linux containers. Refresh that volume after changing
`package-lock.json`:

```bash
docker compose build frontend
docker compose run --rm --no-deps frontend npm ci
```

Stop the stack:

```bash
docker compose down
```

The frontend container serves the browser version of the UI. The Tauri desktop
shell is not run inside Docker because it needs the host display and native OS
integration.

### Configuration

The default host ports are `5173`, `8000`, and `2024`. The frontend and backend
ports can be changed without
editing Compose:

```bash
FRONTEND_PORT=5174 BACKEND_PORT=8080 docker compose up --build
```

The backend reads Nextcloud settings from `backend/dev.env`. For a private CA,
mount the CA file into the backend service and set `NC_CA_BUNDLE` to its
container path. Do not copy credentials into either image.

Docker enables a development-only CORS rule for HTTP(S) origins using the
configured frontend port. Override `NEXGENT_CORS_ORIGIN_REGEX` when a stricter
origin rule is needed.

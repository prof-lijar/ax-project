# Workflow Helper Backend

FastAPI backend for Nextcloud integration.

## Get Started

Install dependencies:

```bash
uv sync --extra dev
```

Create your local environment file:

```bash
cp example.env dev.env
```

Edit `dev.env` and set your Nextcloud app password:

```bash
NC_PASS=your-nextcloud-app-password
```

Load environment variables:

```bash
set -a
source dev.env
set +a
```

Run the server for local access only:

```bash
uv run uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

Run the server for access from another PC on the same network:

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open from another PC, replacing the IP address with this server's LAN IP:

```text
http://192.168.0.18:8000/docs
```

If the browser or `curl` times out from another PC, allow inbound TCP traffic on port `8000`:

```bash
sudo ufw allow from 192.168.0.0/24 to any port 8000 proto tcp
sudo ufw reload
sudo ufw status verbose
```

## Test

```bash
uv run pytest
```

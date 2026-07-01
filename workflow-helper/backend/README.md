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

Run the server:

```bash
uv run uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

## Test

```bash
uv run pytest
```

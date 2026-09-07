FROM python:3.12-slim

RUN pip install --no-cache-dir uv==0.11.26

WORKDIR /app
COPY . .
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "python", "-m", "apps.workers.weekly_report", "serve"]

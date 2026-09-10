# syntax=docker/dockerfile:1
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
RUN groupadd --gid 10001 scout && useradd --uid 10001 --gid scout scout \
    && mkdir -p /app/var && chown scout:scout /app/var
USER scout
EXPOSE 8091
CMD ["uvicorn", "app.fast_api_app:app", "--host", "0.0.0.0", "--port", "8091", "--workers", "1"]

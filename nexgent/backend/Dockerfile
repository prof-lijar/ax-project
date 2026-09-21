# syntax=docker/dockerfile:1.7

ARG UV_VERSION=0.11.32
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:3.12-slim-bookworm

COPY --from=uv /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    AX_CHAT_ARTIFACT_ROOT=/run/ax-chat \
    PATH="/opt/venv/bin:${PATH}"

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        fonts-dejavu-core \
        libreoffice-calc \
        libreoffice-impress \
        libreoffice-writer \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 nexgent \
    && useradd --system --uid 10001 --gid nexgent --create-home nexgent \
    && install --directory --owner=nexgent --group=nexgent --mode=0700 /run/ax-chat /var/lib/nexgent/chat-files

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY --chown=nexgent:nexgent app ./app
COPY --chown=nexgent:nexgent alembic.ini ./alembic.ini
COPY --chown=nexgent:nexgent migrations ./migrations
COPY --chown=nexgent:nexgent --chmod=755 start.sh ./start.sh

USER nexgent

EXPOSE 8000

ENTRYPOINT ["/app/start.sh"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

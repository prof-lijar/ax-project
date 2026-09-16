FROM python:3.12-slim
RUN pip install --no-cache-dir uv==0.11.26
WORKDIR /app
COPY . .
RUN uv sync --frozen --no-dev
EXPOSE 8093
CMD ["uv", "run", "--no-sync", "uvicorn", "apps.sumin.main:create_application", "--factory", "--host", "0.0.0.0", "--port", "8093"]

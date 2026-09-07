FROM python:3.12-slim

RUN pip install --no-cache-dir uv==0.11.26

WORKDIR /app
COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "apps.weekly_report_api.main:app", "--host", "0.0.0.0", "--port", "8080"]

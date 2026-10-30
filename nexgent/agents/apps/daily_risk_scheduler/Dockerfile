FROM python:3.12-alpine

RUN apk add --no-cache tzdata openssh-client sshpass \
    && cp /usr/share/zoneinfo/Asia/Seoul /etc/localtime \
    && echo "Asia/Seoul" > /etc/timezone
WORKDIR /app
RUN pip install --no-cache-dir uv==0.11.26
COPY . .
RUN uv sync --frozen --no-dev \
    && cp apps/daily_risk_scheduler/crontab /etc/crontabs/root
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Seoul
CMD ["crond", "-f", "-l", "2"]

FROM python:3.12-alpine

RUN apk add --no-cache tzdata bash openssh-client sshpass \
    && cp /usr/share/zoneinfo/Asia/Seoul /etc/localtime \
    && echo "Asia/Seoul" > /etc/timezone

WORKDIR /app
RUN pip install --no-cache-dir 'asyncpg>=0.30,<1' 'python-dotenv>=1,<2'
COPY apps/__init__.py /app/apps/__init__.py
COPY playground/weekly-reporter/migrate.sh playground/weekly-reporter/migrate.py /app/playground/weekly-reporter/
COPY apps/weekly_report_scheduler /app/apps/weekly_report_scheduler
COPY apps/weekly_report_scheduler/crontab /etc/crontabs/root

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Seoul

CMD ["crond", "-f", "-l", "2"]

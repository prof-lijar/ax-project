"""Submit the previous completed week to the private bulk control API."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol, Self
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import UUID
from zoneinfo import ZoneInfo

SCHEDULE_TIMEZONE = "Asia/Seoul"
JOBS_PATH = "/v1/weekly-report/bulk/jobs"
MAX_RESPONSE_BYTES = 64 * 1024
VALID_JOB_STATES = {
    "pending",
    "preparing",
    "running",
    "finalizing",
    "completed",
    "partial",
    "failed",
    "cancelling",
    "cancelled",
    "expired",
}


class Response(Protocol):
    status: int

    def read(self, amount: int = -1) -> bytes: ...

    def __enter__(self) -> Self: ...

    def __exit__(self, *args: object) -> None: ...


OpenUrl = Callable[..., Response]
Sleep = Callable[[float], None]
LogEvent = Callable[[dict[str, object]], None]


class SchedulerConfigurationError(ValueError):
    """Safe configuration error without environment values."""


class ScheduledSubmissionError(RuntimeError):
    """Safe terminal submission error without response content."""


@dataclass(frozen=True)
class SchedulerSettings:
    bulk_api_base_url: str = "http://weekly-report-bulk-api:8090"
    max_reports: int = 10_000
    timeout_seconds: float = 30.0
    attempts: int = 3
    retry_delay_seconds: float = 2.0

    @property
    def jobs_url(self) -> str:
        return self.bulk_api_base_url.rstrip("/") + JOBS_PATH

    @classmethod
    def from_env(
        cls, environment: Mapping[str, str] | None = None
    ) -> SchedulerSettings:
        values = os.environ if environment is None else environment
        base_url = values.get(
            "WEEKLY_REPORT_BULK_API_URL",
            "http://weekly-report-bulk-api:8090",
        )
        _validate_base_url(base_url)
        return cls(
            bulk_api_base_url=base_url.rstrip("/"),
            max_reports=_integer_setting(
                values, "WEEKLY_REPORT_SCHEDULE_MAX_REPORTS", 10_000, 1, 10_000
            ),
            timeout_seconds=_float_setting(
                values,
                "WEEKLY_REPORT_SCHEDULE_TIMEOUT_SECONDS",
                30.0,
                1.0,
                120.0,
            ),
            attempts=_integer_setting(
                values, "WEEKLY_REPORT_SCHEDULE_ATTEMPTS", 3, 1, 5
            ),
            retry_delay_seconds=_float_setting(
                values,
                "WEEKLY_REPORT_SCHEDULE_RETRY_DELAY_SECONDS",
                2.0,
                0.0,
                60.0,
            ),
        )


def previous_completed_week_start(
    now: datetime, *, timezone: str = SCHEDULE_TIMEZONE
) -> date:
    """Return the Monday starting the most recent fully completed week."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local_date = now.astimezone(ZoneInfo(timezone)).date()
    current_week_start = local_date - timedelta(days=local_date.weekday())
    return current_week_start - timedelta(days=7)


def build_job_payload(now: datetime, *, max_reports: int) -> dict[str, str | int]:
    week_start = previous_completed_week_start(now)
    return {
        "week_start": week_start.isoformat(),
        "timezone": SCHEDULE_TIMEZONE,
        "max_reports": max_reports,
        "idempotency_key": "cron-weekly-report-" + week_start.isoformat(),
    }


def submit_scheduled_job(
    settings: SchedulerSettings,
    *,
    now: datetime | None = None,
    opener: OpenUrl = urlopen,
    sleeper: Sleep = time.sleep,
    log_event: LogEvent | None = None,
) -> dict[str, Any]:
    requested_at = datetime.now(UTC) if now is None else now
    payload = build_job_payload(requested_at, max_reports=settings.max_reports)
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = Request(
        settings.jobs_url,
        data=encoded,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "ax-weekly-report-cron/1.0",
        },
        method="POST",
    )

    last_error_code = "submission_failed"
    for attempt in range(1, settings.attempts + 1):
        try:
            with opener(request, timeout=settings.timeout_seconds) as response:
                if response.status not in {200, 201}:
                    raise ScheduledSubmissionError(
                        "scheduled bulk submission returned an unexpected status"
                    )
                body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise ScheduledSubmissionError(
                    "scheduled bulk submission response is too large"
                )
            result = _validate_response(body, payload)
            if log_event is not None:
                log_event(
                    {
                        "event": "weekly_report_schedule_submitted",
                        "attempt": attempt,
                        "job_id": result["job_id"],
                        "job_status": result["status"],
                        "week_start": payload["week_start"],
                    }
                )
            return result
        except HTTPError as exc:
            last_error_code = "bulk_api_http_" + str(exc.code)
            retryable = exc.code in {408, 425, 429} or exc.code >= 500
            exc.close()
        except (TimeoutError, URLError):
            last_error_code = "bulk_api_unavailable"
            retryable = True
        except ScheduledSubmissionError:
            raise
        except (OSError, TypeError, ValueError):
            last_error_code = "invalid_bulk_api_response"
            retryable = False

        if not retryable or attempt == settings.attempts:
            break
        delay = settings.retry_delay_seconds * (2 ** (attempt - 1))
        if log_event is not None:
            log_event(
                {
                    "event": "weekly_report_schedule_retry",
                    "attempt": attempt,
                    "error_code": last_error_code,
                    "retry_in_seconds": delay,
                    "week_start": payload["week_start"],
                }
            )
        sleeper(delay)

    raise ScheduledSubmissionError(
        "scheduled bulk submission failed: " + last_error_code
    )


def _validate_response(
    body: bytes, request_payload: Mapping[str, str | int]
) -> dict[str, Any]:
    parsed = json.loads(body.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise TypeError("bulk response must be an object")
    UUID(str(parsed.get("job_id", "")))
    if parsed.get("week_start") != request_payload["week_start"]:
        raise ValueError("bulk response week does not match request")
    if parsed.get("timezone") != request_payload["timezone"]:
        raise ValueError("bulk response timezone does not match request")
    if parsed.get("max_reports") != request_payload["max_reports"]:
        raise ValueError("bulk response report limit does not match request")
    if parsed.get("status") not in VALID_JOB_STATES:
        raise ValueError("bulk response status is invalid")
    return parsed


def _validate_base_url(value: str) -> None:
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise SchedulerConfigurationError(
            "WEEKLY_REPORT_BULK_API_URL must be a credential-free HTTP origin"
        )


def _integer_setting(
    values: Mapping[str, str], name: str, default: int, minimum: int, maximum: int
) -> int:
    try:
        value = int(values.get(name, str(default)))
    except ValueError as exc:
        raise SchedulerConfigurationError(name + " must be an integer") from exc
    if not minimum <= value <= maximum:
        raise SchedulerConfigurationError(name + " is outside the allowed range")
    return value


def _float_setting(
    values: Mapping[str, str],
    name: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    try:
        value = float(values.get(name, str(default)))
    except ValueError as exc:
        raise SchedulerConfigurationError(name + " must be numeric") from exc
    if not minimum <= value <= maximum:
        raise SchedulerConfigurationError(name + " is outside the allowed range")
    return value


def _write_event(event: dict[str, object]) -> None:
    print(json.dumps(event, separators=(",", ":"), sort_keys=True), flush=True)


def main() -> int:
    try:
        settings = SchedulerSettings.from_env()
        submit_scheduled_job(settings, log_event=_write_event)
    except (SchedulerConfigurationError, ScheduledSubmissionError) as exc:
        _write_event(
            {
                "event": "weekly_report_schedule_failed",
                "error": str(exc),
            }
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

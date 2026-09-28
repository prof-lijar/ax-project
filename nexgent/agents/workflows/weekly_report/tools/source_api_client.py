"""Typed HTTP client for the private weekly-report source API."""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from ax_contracts import WeeklyReportRequest, WeeklyReportSourceResponse
from pydantic import ValidationError

from workflows.weekly_report.diagnostics import SOURCE_JOB_ID

_LOG = logging.getLogger(__name__)
_MAX_ATTEMPTS = 3
_retry_sleep = asyncio.sleep


class WeeklyReportSourceError(RuntimeError):
    """Safe source-service failure exposed to graph orchestration."""

    def __init__(
        self,
        *,
        error_code: str,
        cause_type: str,
        attempts: int,
        retryable: bool,
        http_status: int | None = None,
    ) -> None:
        super().__init__("weekly-report source API is unavailable")
        self.error_code = error_code
        self.cause_type = cause_type
        self.attempts = attempts
        self.retryable = retryable
        self.http_status = http_status


@dataclass(frozen=True, slots=True)
class SourceApiSettings:
    base_url: str
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("WEEKLY_REPORT_SOURCE_URL must be an HTTP(S) URL")
        if (
            not math.isfinite(self.timeout_seconds)
            or not 0 < self.timeout_seconds <= 120
        ):
            raise ValueError("weekly-report source timeout must be in (0, 120]")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> SourceApiSettings:
        values = os.environ if environ is None else environ
        return cls(
            base_url=values.get("WEEKLY_REPORT_SOURCE_URL", ""),
            timeout_seconds=float(
                values.get("WEEKLY_REPORT_SOURCE_TIMEOUT_SECONDS", "30")
            ),
        )


class WeeklyReportSourceApiClient:
    def __init__(
        self,
        settings: SourceApiSettings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.timeout_seconds),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def load(self, request: WeeklyReportRequest) -> WeeklyReportSourceResponse:
        # This POST only reads source data. Retry the same page before staging it.
        payload = request.model_dump(mode="json")
        started = time.monotonic()
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            metadata = {
                "job_id": SOURCE_JOB_ID.get(),
                "week_start": request.week_start.isoformat(),
                "stage": "source",
                "attempt": attempt,
                "max_attempts": _MAX_ATTEMPTS,
                "timeout_seconds": self.settings.timeout_seconds,
            }
            _LOG.info("weekly_report_source_started", extra=metadata)
            try:
                response = await asyncio.wait_for(
                    self._client.post(
                        self.settings.base_url.rstrip("/")
                        + "/internal/v1/weekly-report/source",
                        json=payload,
                    ),
                    timeout=self.settings.timeout_seconds,
                )
                response.raise_for_status()
                result = WeeklyReportSourceResponse.model_validate(response.json())
            except (httpx.HTTPError, TimeoutError, ValueError) as exc:
                status = (
                    exc.response.status_code
                    if isinstance(exc, httpx.HTTPStatusError)
                    else None
                )
                retryable = isinstance(
                    exc, (httpx.TimeoutException, httpx.NetworkError, TimeoutError)
                ) or (
                    status is not None
                    and (status in {408, 429} or 500 <= status <= 599)
                )
                if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
                    code = "source_timeout"
                elif status is not None:
                    code = "source_http_error"
                elif isinstance(exc, (ValueError, ValidationError)):
                    code = "source_invalid_response"
                else:
                    code = "source_transport_error"
                failure = WeeklyReportSourceError(
                    error_code=code,
                    cause_type=type(exc).__name__,
                    attempts=attempt,
                    retryable=retryable,
                    http_status=status,
                )
                metadata.update(
                    error_code=code,
                    error_type=type(exc).__name__,
                    http_status=status,
                    retryable=retryable,
                    elapsed_seconds=round(time.monotonic() - started, 3),
                )
                if not retryable or attempt == _MAX_ATTEMPTS:
                    _LOG.error("weekly_report_source_failed", extra=metadata)
                    raise failure from exc
                delay = float(2**attempt)
                _LOG.warning(
                    "weekly_report_source_retry",
                    extra={
                        **metadata,
                        "retry_in_seconds": delay,
                    },
                )
                await _retry_sleep(delay)
            else:
                _LOG.info(
                    "weekly_report_source_completed",
                    extra={
                        **metadata,
                        "report_count": len(result.items),
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                    },
                )
                return result
        raise AssertionError("source attempts exhausted without an outcome")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

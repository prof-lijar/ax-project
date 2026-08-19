"""Typed HTTP client for the private weekly-report source API."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from ax_contracts import WeeklyReportRequest, WeeklyReportSourceResponse
from pydantic import ValidationError


class WeeklyReportSourceError(RuntimeError):
    """Safe source-service failure exposed to graph orchestration."""


@dataclass(frozen=True, slots=True)
class SourceApiSettings:
    base_url: str
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("WEEKLY_REPORT_SOURCE_URL must be an HTTP(S) URL")
        if self.timeout_seconds <= 0:
            raise ValueError("weekly-report source timeout must be positive")

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
        try:
            response = await self._client.post(
                self.settings.base_url.rstrip("/")
                + "/internal/v1/weekly-report/source",
                json=request.model_dump(mode="json"),
            )
            response.raise_for_status()
            return WeeklyReportSourceResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            raise WeeklyReportSourceError("weekly-report source API is unavailable") from exc

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

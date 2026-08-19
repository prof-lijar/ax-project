from datetime import date

import httpx
import pytest

from apps.weekly_report_api.app import create_app
from workflows.weekly_report.tools.source_repository import (
    MockWeeklyReportSourceRepository,
)


class FakeSourceService:
    def __init__(self) -> None:
        self.repository = MockWeeklyReportSourceRepository()

    async def health(self) -> bool:
        return True

    async def build(self, request):
        return await self.repository.load(request)


@pytest.mark.asyncio
async def test_private_source_api_returns_versioned_metrics() -> None:
    app = create_app(service=FakeSourceService())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/health/live")).status_code == 200
        assert (await client.get("/health/ready")).status_code == 200
        response = await client.post(
            "/internal/v1/weekly-report/source",
            json={"week_start": "2026-08-03", "ward_ids": [101]},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "1"
    assert payload["week_start"] == date(2026, 8, 3).isoformat()
    assert payload["items"][0]["current"]["danger_days"] >= 0


@pytest.mark.asyncio
async def test_private_source_api_rejects_invalid_period() -> None:
    app = create_app(service=FakeSourceService())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/internal/v1/weekly-report/source",
            json={"week_start": "2026-08-04"},
        )
    assert response.status_code == 422

from __future__ import annotations

from pathlib import Path

import httpx

from app.fast_api_app import create_app
from app.models import FetchedPage, ScoutRunRequest, ScoutRunResponse, SearchPlan, SearchResult
from app.services.persistence import ArtifactStore
from app.services.run_service import ScoutRunService


class StubRunService:
    def __init__(self, *, ready: bool = True, fail: bool = False) -> None:
        self._ready = ready
        self._fail = fail

    def is_ready(self) -> bool:
        return self._ready

    async def run(self, request: ScoutRunRequest) -> ScoutRunResponse:
        if self._fail:
            raise RuntimeError("private upstream detail")
        return ScoutRunResponse(
            run_id="0123456789abcdef0123456789abcdef",
            status="success",
            report=f"# Scout Report\n\n## Topic\n\n{request.topic}",
            sources=["https://example.com/article"],
            report_artifact="runs/0123456789abcdef0123456789abcdef/report.md",
            log_artifact="runs/0123456789abcdef0123456789abcdef/execution.jsonl",
        )


class MockStages:
    async def create_search_plan(
        self,
        request: ScoutRunRequest,
        run_id: str,
    ) -> SearchPlan:
        del request, run_id
        return SearchPlan(queries=["mock query"])

    async def create_summary(
        self,
        request: ScoutRunRequest,
        run_id: str,
        evidence: list[FetchedPage],
    ) -> str:
        del run_id
        source = evidence[0].url
        return f"""# Scout Report

## Topic

{request.topic}

## Summary

Mocked evidence summary.

## Key Findings

- Evidence was fetched before use.

## Sources

- [Fetched evidence]({source})
"""


class MockSearchProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        del limit
        self.calls.append(query)
        return [
            SearchResult(
                title="Fetched evidence",
                url="https://example.com/evidence",
                snippet="Discovery hint",
            )
        ]


class MockFetcher:
    async def fetch(self, url: str) -> FetchedPage:
        return FetchedPage(
            url=url,
            title="Fetched evidence",
            text="Evidence obtained from the selected public page.",
            content_type="text/html",
            truncated=False,
        )

    async def aclose(self) -> None:
        return None


async def request(app, method: str, path: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.request(method, path, **kwargs)


async def test_health_endpoints() -> None:
    app = create_app(run_service=StubRunService())

    live = await request(app, "GET", "/health/live")
    ready = await request(app, "GET", "/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}


async def test_ready_returns_503_when_model_configuration_is_missing() -> None:
    app = create_app(run_service=StubRunService(ready=False))

    response = await request(app, "GET", "/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Scout service is not configured."}


async def test_run_request_validation_and_success_contract() -> None:
    app = create_app(run_service=StubRunService())

    invalid = await request(app, "POST", "/v1/scout/runs", json={"topic": "  "})
    response = await request(
        app,
        "POST",
        "/v1/scout/runs",
        json={"topic": " Example research ", "keywords": [" alpha ", "alpha"]},
    )

    assert invalid.status_code == 422
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["run_id"] == "0123456789abcdef0123456789abcdef"
    assert payload["sources"] == ["https://example.com/article"]
    assert payload["report_artifact"].endswith("/report.md")
    assert payload["log_artifact"].endswith("/execution.jsonl")


async def test_post_runs_deterministic_web_between_mocked_llm_stages(tmp_path: Path) -> None:
    provider = MockSearchProvider()
    service = ScoutRunService(
        artifact_store=ArtifactStore(tmp_path),
        stages=MockStages(),
        search_provider=provider,
        fetcher=MockFetcher(),
        search_result_limit=6,
        fetch_page_limit=3,
    )
    app = create_app(run_service=service)

    response = await request(
        app,
        "POST",
        "/v1/scout/runs",
        json={"topic": "Mocked full cycle", "keywords": ["evidence"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert provider.calls == ["mock query"]
    assert payload["sources"] == ["https://example.com/evidence"]
    assert (tmp_path / payload["report_artifact"]).is_file()
    assert (tmp_path / payload["log_artifact"]).is_file()


async def test_run_failure_returns_safe_error_without_false_success() -> None:
    app = create_app(run_service=StubRunService(fail=True))

    response = await request(
        app,
        "POST",
        "/v1/scout/runs",
        json={"topic": "Example research"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Scout run failed."}
    assert "private upstream detail" not in response.text

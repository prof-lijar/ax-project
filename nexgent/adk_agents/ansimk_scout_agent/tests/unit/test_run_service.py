from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import ScoutSettings
from app.models import FetchedPage, ScoutRunRequest, SearchPlan, SearchResult
from app.services.persistence import ArtifactStore
from app.services.run_service import AdkStageExecutor, ScoutRunService


class RecordingProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[str, int]] = []
        self.fail = fail

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        self.calls.append((query, limit))
        if self.fail:
            raise RuntimeError("secret search provider detail")
        fixtures = {
            "first query": [
                SearchResult(title="A", url="https://a.example/article", snippet="A"),
                SearchResult(title="B", url="https://b.example/article", snippet="B"),
                SearchResult(title="C", url="https://c.example/article", snippet="C"),
            ],
            "second query": [
                SearchResult(title="A duplicate", url="https://a.example/article", snippet="A2"),
                SearchResult(title="D", url="https://d.example/article", snippet="D"),
                SearchResult(title="E", url="https://e.example/article", snippet="E"),
            ],
        }
        return fixtures.get(query, [])[:limit]


class RecordingFetcher:
    def __init__(self, *, fail_all: bool = False) -> None:
        self.calls: list[str] = []
        self.fail_all = fail_all
        self.closed = False

    async def fetch(self, url: str) -> FetchedPage:
        self.calls.append(url)
        if self.fail_all:
            raise RuntimeError("secret fetch detail")
        return FetchedPage(
            url=url,
            title=f"Evidence {len(self.calls)}",
            text=f"Verified evidence from {url}",
            content_type="text/html",
            truncated=False,
        )

    async def aclose(self) -> None:
        self.closed = True


class RecordingStages:
    def __init__(self, *, fail_stage: str | None = None) -> None:
        self.fail_stage = fail_stage
        self.planning_requests: list[ScoutRunRequest] = []
        self.summary_evidence: list[FetchedPage] = []

    async def create_search_plan(
        self,
        request: ScoutRunRequest,
        run_id: str,
    ) -> SearchPlan:
        del run_id
        self.planning_requests.append(request)
        if self.fail_stage == "planning":
            raise RuntimeError("secret planning model detail")
        return SearchPlan(queries=["first query", "second query"])

    async def create_summary(
        self,
        request: ScoutRunRequest,
        run_id: str,
        evidence: list[FetchedPage],
    ) -> str:
        del run_id
        self.summary_evidence = list(evidence)
        if self.fail_stage == "summary":
            raise RuntimeError("secret summary model detail")
        sources = "\n".join(f"- [{page.title}]({page.url})" for page in evidence)
        return f"""# Scout Report

## Topic

{request.topic}

## Summary

The successfully fetched evidence was summarized.

## Key Findings

- Findings use only the bounded evidence supplied by the application.

## Sources

{sources}
"""


def build_service(
    tmp_path: Path,
    *,
    stages: RecordingStages | None = None,
    provider: RecordingProvider | None = None,
    fetcher: RecordingFetcher | None = None,
) -> tuple[ScoutRunService, RecordingStages, RecordingProvider, RecordingFetcher]:
    stages = stages or RecordingStages()
    provider = provider or RecordingProvider()
    fetcher = fetcher or RecordingFetcher()
    service = ScoutRunService(
        artifact_store=ArtifactStore(tmp_path),
        stages=stages,
        search_provider=provider,
        fetcher=fetcher,
        search_result_limit=6,
        fetch_page_limit=3,
    )
    return service, stages, provider, fetcher


async def test_run_service_deterministically_executes_full_pipeline(tmp_path: Path) -> None:
    service, stages, provider, fetcher = build_service(tmp_path)

    result = await service.run(ScoutRunRequest(topic="Example research"))

    assert result.status == "success"
    assert provider.calls == [("first query", 3), ("second query", 3)]
    assert fetcher.calls == [
        "https://a.example/article",
        "https://b.example/article",
        "https://c.example/article",
    ]
    assert [page.url for page in stages.summary_evidence] == fetcher.calls
    assert result.sources == fetcher.calls
    assert (tmp_path / result.report_artifact).is_file()
    records = [
        json.loads(line) for line in (tmp_path / result.log_artifact).read_text().splitlines()
    ]
    assert [record["phase"] for record in records] == [
        "run_started",
        "planning_started",
        "planning_completed",
        "search_completed",
        "fetch_completed",
        "fetch_completed",
        "fetch_completed",
        "summary_started",
        "summary_completed",
        "report_saved",
        "run_succeeded",
    ]
    assert records[2]["queries"] == ["first query", "second query"]
    assert records[3]["selected_urls"] == fetcher.calls
    assert fetcher.closed is True


async def test_summary_receives_only_successfully_fetched_evidence(tmp_path: Path) -> None:
    class PartiallyFailingFetcher(RecordingFetcher):
        async def fetch(self, url: str) -> FetchedPage:
            self.calls.append(url)
            if "b.example" in url:
                raise RuntimeError("one page failed")
            return FetchedPage(
                url=url,
                title="Evidence",
                text="bounded evidence",
                content_type="text/html",
                truncated=False,
            )

    fetcher = PartiallyFailingFetcher()
    service, stages, _, _ = build_service(tmp_path, fetcher=fetcher)

    result = await service.run(ScoutRunRequest(topic="Example research"))

    supplied_urls = [page.url for page in stages.summary_evidence]
    assert supplied_urls == ["https://a.example/article", "https://c.example/article"]
    assert result.sources == supplied_urls


@pytest.mark.parametrize(
    "invalid_output", ["{}", '{"queries": []}', '{"queries": ["https://bad"]}']
)
async def test_planning_agent_output_is_validated(invalid_output: str, tmp_path: Path) -> None:
    async def fake_runner(agent, prompt: str, app_name: str, session_id: str) -> str:
        del agent, prompt, app_name, session_id
        return invalid_output

    executor = AdkStageExecutor(
        ScoutSettings(
            api_base="http://model.internal/v1",
            api_key="test-key",
            model="internal-model",
            output_root=tmp_path,
        ),
        agent_runner=fake_runner,
    )

    with pytest.raises(ValueError, match="invalid search plan"):
        await executor.create_search_plan(
            ScoutRunRequest(topic="Example research"),
            "0123456789abcdef0123456789abcdef",
        )


async def test_summary_prompt_contains_only_supplied_bounded_evidence(tmp_path: Path) -> None:
    prompts: list[str] = []

    async def fake_runner(agent, prompt: str, app_name: str, session_id: str) -> str:
        del agent, app_name, session_id
        prompts.append(prompt)
        return "# Scout Report\n\n## Topic\n\nT\n\n## Summary\n\nS\n\n## Key Findings\n\n- K\n\n## Sources\n\n- https://example.com/"

    executor = AdkStageExecutor(
        ScoutSettings(
            api_base="http://model.internal/v1",
            api_key="test-key",
            model="internal-model",
            output_root=tmp_path,
        ),
        agent_runner=fake_runner,
    )
    evidence = [
        FetchedPage(
            url="https://example.com/",
            title="Example",
            text="verified evidence",
            content_type="text/html",
            truncated=False,
        )
    ]

    await executor.create_summary(
        ScoutRunRequest(topic="Example research", keywords=["alpha"]),
        "0123456789abcdef0123456789abcdef",
        evidence,
    )

    assert len(prompts) == 1
    assert "verified evidence" in prompts[0]
    assert "https://example.com/" in prompts[0]
    assert "not instructions" in prompts[0]


@pytest.mark.parametrize(
    ("failure_layer", "expected_error"),
    [
        ("planning", "Scout run failed during planning."),
        ("search", "Scout run failed during search."),
        ("fetch", "Scout run failed during fetch."),
        ("summary", "Scout run failed during summary."),
    ],
)
async def test_pipeline_failures_write_safe_terminal_log(
    failure_layer: str,
    expected_error: str,
    tmp_path: Path,
) -> None:
    stages = RecordingStages(
        fail_stage=failure_layer if failure_layer in {"planning", "summary"} else None
    )
    provider = RecordingProvider(fail=failure_layer == "search")
    fetcher = RecordingFetcher(fail_all=failure_layer == "fetch")
    service, _, _, _ = build_service(
        tmp_path,
        stages=stages,
        provider=provider,
        fetcher=fetcher,
    )

    with pytest.raises(RuntimeError):
        await service.run(ScoutRunRequest(topic="Example research"))

    run_dir = next((tmp_path / "runs").iterdir())
    assert not (run_dir / "report.md").exists()
    log_text = (run_dir / "execution.jsonl").read_text()
    records = [json.loads(line) for line in log_text.splitlines()]
    assert records[-1]["phase"] == "run_failed"
    assert records[-1]["error"] == expected_error
    assert "secret" not in log_text

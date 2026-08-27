from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models import FetchedPage, ScoutRunRequest, SearchResult
from app.services.persistence import ArtifactStore, ReportValidationError
from app.services.run_service import AgentExecution, ScoutRunService
from app.tools.scout import ScoutWebToolset


class RecordingProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[str, int]] = []
        self.fail = fail

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        self.calls.append((query, limit))
        if self.fail:
            raise RuntimeError("secret search provider detail")
        return [
            SearchResult(title="A", url="https://a.example/article", snippet="hint"),
            SearchResult(title="B", url="https://b.example/article", snippet="hint"),
        ][:limit]


class RecordingFetcher:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[str] = []
        self.fail = fail
        self.closed = False

    async def fetch(self, url: str) -> FetchedPage:
        self.calls.append(url)
        if self.fail:
            raise RuntimeError("secret fetch detail")
        return FetchedPage(
            url=url,
            title="Evidence",
            text=f"Verified evidence from {url}",
            content_type="text/html",
            truncated=False,
        )

    async def aclose(self) -> None:
        self.closed = True


class ControlledToolCallingExecutor:
    def __init__(
        self,
        *,
        fail: bool = False,
        cite_unfetched: bool = False,
        skip_fetch: bool = False,
    ) -> None:
        self.fail = fail
        self.cite_unfetched = cite_unfetched
        self.skip_fetch = skip_fetch
        self.requests: list[ScoutRunRequest] = []

    async def execute(
        self,
        request: ScoutRunRequest,
        run_id: str,
        toolset: ScoutWebToolset,
    ) -> AgentExecution:
        del run_id
        self.requests.append(request)
        if self.fail:
            raise RuntimeError("secret model detail")
        search_response = await toolset.web_search("bounded query")
        tool_calls = ["web_search"]
        if not self.skip_fetch:
            first_result = search_response["results"][0]
            await toolset.web_fetch_and_extract(first_result["url"])
            tool_calls.append("web_fetch_and_extract")
        source = (
            "https://unfetched.example/article"
            if self.cite_unfetched or self.skip_fetch
            else "https://a.example/article"
        )
        report = f"""# Scout Report

## Topic

{request.topic}

## Summary

The successfully fetched evidence was summarized.

## Key Findings

- Findings use only evidence returned by the bounded fetch tool.

## Sources

- [Evidence]({source})
"""
        return AgentExecution(report=report, tool_calls=tuple(tool_calls))


def build_service(
    tmp_path: Path,
    *,
    executor: ControlledToolCallingExecutor | None = None,
    provider: RecordingProvider | None = None,
    fetcher: RecordingFetcher | None = None,
) -> tuple[
    ScoutRunService,
    ControlledToolCallingExecutor,
    RecordingProvider,
    RecordingFetcher,
]:
    artifact_store = ArtifactStore(tmp_path)
    executor = executor or ControlledToolCallingExecutor()
    provider = provider or RecordingProvider()
    fetcher = fetcher or RecordingFetcher()

    def create_toolset(run_id: str) -> ScoutWebToolset:
        return ScoutWebToolset(
            run_id=run_id,
            event_logger=artifact_store,
            search_provider=provider,
            fetcher=fetcher,
            max_search_calls=3,
            search_result_limit=6,
            max_fetch_calls=3,
        )

    service = ScoutRunService(
        artifact_store=artifact_store,
        agent_executor=executor,
        toolset_factory=create_toolset,
    )
    return service, executor, provider, fetcher


async def test_run_service_persists_single_agent_function_tool_pipeline(tmp_path: Path) -> None:
    service, executor, provider, fetcher = build_service(tmp_path)

    result = await service.run(ScoutRunRequest(topic="Example research"))

    assert result.status == "success"
    assert len(executor.requests) == 1
    assert provider.calls == [("bounded query", 6)]
    assert fetcher.calls == ["https://a.example/article"]
    assert result.sources == fetcher.calls
    assert (tmp_path / result.report_artifact).is_file()
    records = [
        json.loads(line) for line in (tmp_path / result.log_artifact).read_text().splitlines()
    ]
    assert [record["phase"] for record in records] == [
        "run_started",
        "agent_started",
        "search_started",
        "search_completed",
        "fetch_started",
        "fetch_completed",
        "agent_completed",
        "report_saved",
        "run_succeeded",
    ]
    assert records[1]["registered_tools"] == ["web_search", "web_fetch_and_extract"]
    assert records[6]["tool_names"] == ["web_search", "web_fetch_and_extract"]
    assert fetcher.closed is True


async def test_report_validation_rejects_agent_citation_not_fetched_by_tool(
    tmp_path: Path,
) -> None:
    service, _, _, _ = build_service(
        tmp_path,
        executor=ControlledToolCallingExecutor(cite_unfetched=True),
    )

    with pytest.raises(ReportValidationError, match="not fetched"):
        await service.run(ScoutRunRequest(topic="Example research"))

    run_dir = next((tmp_path / "runs").iterdir())
    assert not (run_dir / "report.md").exists()
    records = [json.loads(line) for line in (run_dir / "execution.jsonl").read_text().splitlines()]
    assert records[-1]["phase"] == "run_failed"
    assert records[-1]["error"] == "Scout run failed during report validation."


async def test_no_successful_fetch_cannot_produce_success(tmp_path: Path) -> None:
    service, _, _, _ = build_service(
        tmp_path,
        executor=ControlledToolCallingExecutor(skip_fetch=True),
    )

    with pytest.raises(ReportValidationError, match="not fetched"):
        await service.run(ScoutRunRequest(topic="Example research"))


async def test_agent_failure_writes_safe_terminal_log(tmp_path: Path) -> None:
    service, _, _, fetcher = build_service(
        tmp_path,
        executor=ControlledToolCallingExecutor(fail=True),
    )

    with pytest.raises(RuntimeError, match="secret model detail"):
        await service.run(ScoutRunRequest(topic="Example research"))

    run_dir = next((tmp_path / "runs").iterdir())
    assert not (run_dir / "report.md").exists()
    log_text = (run_dir / "execution.jsonl").read_text()
    records = [json.loads(line) for line in log_text.splitlines()]
    assert records[-1]["phase"] == "run_failed"
    assert records[-1]["error"] == "Scout run failed during agent."
    assert "secret" not in log_text
    assert fetcher.closed is True


async def test_search_and_fetch_failures_are_safe_tool_responses(tmp_path: Path) -> None:
    artifact_store = ArtifactStore(tmp_path)
    run_id = artifact_store.create_run()
    tools = ScoutWebToolset(
        run_id=run_id,
        event_logger=artifact_store,
        search_provider=RecordingProvider(fail=True),
        fetcher=RecordingFetcher(fail=True),
        max_search_calls=1,
        search_result_limit=1,
        max_fetch_calls=1,
    )

    search_result = await tools.web_search("query")
    fetch_result = await tools.web_fetch_and_extract("https://not-searched.example/")

    assert search_result["error_code"] == "search_failed"
    assert fetch_result["error_code"] == "url_not_in_search_results"
    log_text = (tmp_path / "runs" / run_id / "execution.jsonl").read_text()
    assert "secret" not in log_text

from __future__ import annotations

from app.models import FetchedPage, SearchResult
from app.tools.scout import ScoutWebToolset


class RecordingLogger:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def append_event(self, run_id: str, phase: str, **metadata: object) -> None:
        self.events.append({"run_id": run_id, "phase": phase, **metadata})


class RecordingProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        self.calls.append((query, limit))
        suffix = len(self.calls)
        return [
            SearchResult(
                title=f"Result {suffix}",
                url=f"https://example.com/evidence-{suffix}",
                snippet="Discovery only",
            )
        ]


class RecordingFetcher:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.closed = False

    async def fetch(self, url: str) -> FetchedPage:
        self.calls.append(url)
        return FetchedPage(
            url=url,
            title="Evidence",
            text="Bounded extracted evidence.",
            content_type="text/html",
            truncated=False,
        )

    async def aclose(self) -> None:
        self.closed = True


def build_toolset(
    *,
    max_search_calls: int = 2,
    search_result_limit: int = 6,
    max_fetch_calls: int = 2,
) -> tuple[ScoutWebToolset, RecordingLogger, RecordingProvider, RecordingFetcher]:
    logger = RecordingLogger()
    provider = RecordingProvider()
    fetcher = RecordingFetcher()
    tools = ScoutWebToolset(
        run_id="run-1",
        event_logger=logger,
        search_provider=provider,
        fetcher=fetcher,
        max_search_calls=max_search_calls,
        search_result_limit=search_result_limit,
        max_fetch_calls=max_fetch_calls,
    )
    return tools, logger, provider, fetcher


async def test_search_budget_is_enforced_in_python_tool() -> None:
    tools, logger, provider, _ = build_toolset(max_search_calls=2)

    first = await tools.web_search("first query")
    second = await tools.web_search("second query")
    exhausted = await tools.web_search("third query")

    assert first["status"] == "success"
    assert second["status"] == "success"
    assert exhausted == {
        "status": "error",
        "error_code": "search_budget_exhausted",
        "message": "Search call budget is exhausted.",
    }
    assert provider.calls == [("first query", 6), ("second query", 5)]
    assert tools.search_call_count == 2
    assert [event["phase"] for event in logger.events].count("search_started") == 3


async def test_search_result_budget_and_cross_call_deduplication_are_enforced() -> None:
    class DuplicateProvider(RecordingProvider):
        async def search(self, query: str, limit: int) -> list[SearchResult]:
            self.calls.append((query, limit))
            return [
                SearchResult(title="A", url="https://example.com/a?utm_source=test"),
                SearchResult(title="B", url="https://example.com/b"),
                SearchResult(title="A duplicate", url="https://example.com/a"),
            ][:limit]

    logger = RecordingLogger()
    provider = DuplicateProvider()
    tools = ScoutWebToolset(
        run_id="run-1",
        event_logger=logger,
        search_provider=provider,
        fetcher=RecordingFetcher(),
        max_search_calls=3,
        search_result_limit=2,
        max_fetch_calls=2,
    )

    first = await tools.web_search("query")
    second = await tools.web_search("another query")

    assert [result["url"] for result in first["results"]] == [
        "https://example.com/a",
        "https://example.com/b",
    ]
    assert second["error_code"] == "result_budget_exhausted"
    assert provider.calls == [("query", 2)]


async def test_fetch_requires_searched_url_tracks_success_and_enforces_budget() -> None:
    tools, logger, _, fetcher = build_toolset(max_fetch_calls=2)
    await tools.web_search("evidence")

    rejected = await tools.web_fetch_and_extract("https://not-searched.example/item")
    success = await tools.web_fetch_and_extract("https://example.com/evidence-1")
    exhausted = await tools.web_fetch_and_extract("https://example.com/evidence-1")

    assert rejected["error_code"] == "url_not_in_search_results"
    assert success["status"] == "success"
    assert success["page"]["content_is_untrusted"] is True
    assert exhausted["error_code"] == "fetch_budget_exhausted"
    assert fetcher.calls == ["https://example.com/evidence-1"]
    assert tools.fetch_call_count == 2
    assert tools.successful_fetched_urls == {"https://example.com/evidence-1"}
    assert [event["phase"] for event in logger.events].count("fetch_completed") == 3


async def test_tool_logs_do_not_include_fetched_page_body() -> None:
    tools, logger, _, _ = build_toolset()
    await tools.web_search("evidence")
    await tools.web_fetch_and_extract("https://example.com/evidence-1")

    assert "Bounded extracted evidence." not in repr(logger.events)

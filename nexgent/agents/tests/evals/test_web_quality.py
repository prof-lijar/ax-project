"""Opt-in live quality smoke tests for nondeterministic no-key search engines."""

import os
import time

import pytest
from ax_contracts import WebFetchInput, WebSearchInput
from ax_integrations import (
    SafeWebFetchClient,
    SearxngSearchClient,
    SearxngSettings,
    WebRetrievalError,
)

pytestmark = pytest.mark.skipif(
    os.getenv("AX_RUN_LIVE_WEB_EVALS") != "1",
    reason="set AX_RUN_LIVE_WEB_EVALS=1 with a reachable SearXNG service",
)


@pytest.mark.asyncio
async def test_live_search_quality_and_fetch_success() -> None:
    search = SearxngSearchClient(SearxngSettings.from_env())
    fetch = SafeWebFetchClient()
    cases = [
        WebSearchInput(
            query="latest LangGraph release notes",
            language="en",
            allowed_domains=["langchain.com"],
        ),
        WebSearchInput(
            query="OpenAI web search official documentation",
            language="en",
            allowed_domains=["openai.com"],
        ),
        WebSearchInput(
            query="latest artificial intelligence news",
            language="en",
            time_range="day",
        ),
        WebSearchInput(query="대한민국 인공지능 정책 최신", language="ko"),
    ]
    metrics: list[dict[str, object]] = []
    fetch_successes = 0

    try:
        for case in cases:
            started = time.perf_counter()
            output = await search.search(case)
            latency = time.perf_counter() - started
            urls = [result.url for result in output.results]
            domains = {result.domain for result in output.results}
            assert urls, f"no results for {case.query!r}: {output.warnings}"
            assert len(urls) == len(set(urls))
            metrics.append(
                {
                    "query": case.query,
                    "result_count": len(urls),
                    "unique_domains": len(domains),
                    "duplicate_rate": 1 - (len(set(urls)) / len(urls)),
                    "latency_seconds": round(latency, 3),
                }
            )
            try:
                page = await fetch.fetch(
                    WebFetchInput(url=output.results[0].url, max_characters=4_000)
                )
            except WebRetrievalError:
                continue
            if page.text and page.content_is_untrusted:
                fetch_successes += 1
    finally:
        await search.aclose()
        await fetch.aclose()

    assert fetch_successes >= 2, {"metrics": metrics, "fetch_successes": fetch_successes}

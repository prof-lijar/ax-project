import asyncio
import json
import logging
from datetime import date
from unittest.mock import AsyncMock

import httpx
import pytest
from ax_contracts import WeeklyReportRequest, WeeklyReportSourceResponse
from ax_observability.logging import JsonDiagnosticFormatter

from workflows.weekly_report.diagnostics import DIAGNOSTIC_FIELDS, SOURCE_JOB_ID
from workflows.weekly_report.tools import source_api_client as source

REQUEST = WeeklyReportRequest(week_start=date(2026, 9, 21), limit=100)
BODY = WeeklyReportSourceResponse(
    week_start=REQUEST.week_start,
    week_end=REQUEST.week_end,
    timezone=REQUEST.timezone,
    items=[],
).model_dump(mode="json")


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "network", 408, 429, 500, 503])
async def test_transient_failure_retries_identical_page_then_succeeds(
    failure,
    monkeypatch,
    caplog,
):
    calls = []
    sleep = AsyncMock()
    monkeypatch.setattr(source, "_retry_sleep", sleep)

    def handle(request):
        calls.append(request.content)
        if len(calls) < 3:
            if failure == "timeout":
                raise httpx.ReadTimeout("private exception content")
            if failure == "network":
                raise httpx.ConnectError("private exception content")
            return httpx.Response(failure, text="private response content")
        return httpx.Response(200, json=BODY)

    caplog.set_level(logging.INFO)
    token = SOURCE_JOB_ID.set("test-job")
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            result = await source.WeeklyReportSourceApiClient(
                source.SourceApiSettings("http://source"),
                client=http,
            ).load(REQUEST)
    finally:
        SOURCE_JOB_ID.reset(token)
    assert result.items == []
    assert len(calls) == 3 and calls[0] == calls[1] == calls[2]
    assert [call.args[0] for call in sleep.await_args_list] == [2, 4]
    events = [r for r in caplog.records if r.name == source.__name__]
    assert [r.attempt for r in events if r.msg == "weekly_report_source_retry"] == [
        1,
        2,
    ]
    assert events[-1].msg == "weekly_report_source_completed"
    assert all(r.job_id == "test-job" for r in events)
    encoded = "\n".join(
        JsonDiagnosticFormatter(DIAGNOSTIC_FIELDS).format(r) for r in events
    )
    assert "private" not in encoded and "http://source" not in encoded


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,body",
    [(400, {}), (401, {}), (403, {}), (422, {}), (200, {}), (200, "invalid-json")],
)
async def test_permanent_errors_are_not_retried(status, body, monkeypatch):
    calls = []
    sleep = AsyncMock()
    monkeypatch.setattr(source, "_retry_sleep", sleep)

    def handle(request):
        calls.append(request)
        if isinstance(body, str):
            return httpx.Response(status, text=body)
        return httpx.Response(status, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        with pytest.raises(source.WeeklyReportSourceError) as caught:
            await source.WeeklyReportSourceApiClient(
                source.SourceApiSettings("http://source"),
                client=http,
            ).load(REQUEST)
    assert len(calls) == 1
    assert caught.value.retryable is False
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_timeout_exhaustion_is_bounded_and_preserves_safe_cause(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr(source, "_retry_sleep", sleep)
    http = AsyncMock()
    http.post.side_effect = httpx.ConnectTimeout("secret-url-and-token")
    client = source.WeeklyReportSourceApiClient(
        source.SourceApiSettings("http://source"), client=http
    )
    with pytest.raises(source.WeeklyReportSourceError) as caught:
        await client.load(REQUEST)
    assert http.post.await_count == 3
    assert caught.value.attempts == 3
    assert caught.value.error_code == "source_timeout"
    assert caught.value.cause_type == "ConnectTimeout"
    assert "secret" not in str(caught.value)


@pytest.mark.asyncio
async def test_attempt_deadline_bounds_even_nonresponsive_transport(monkeypatch):
    calls = 0

    async def handle(request):
        nonlocal calls
        calls += 1
        await asyncio.Event().wait()

    monkeypatch.setattr(source, "_retry_sleep", AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = source.WeeklyReportSourceApiClient(
            source.SourceApiSettings("http://source", timeout_seconds=0.01),
            client=http,
        )
        with pytest.raises(source.WeeklyReportSourceError) as caught:
            await asyncio.wait_for(client.load(REQUEST), 1)
    assert calls == 3
    assert caught.value.error_code == "source_timeout"


@pytest.mark.asyncio
@pytest.mark.parametrize("during_backoff", [False, True])
async def test_cancellation_propagates_without_another_attempt(
    during_backoff, monkeypatch
):
    http = AsyncMock()
    http.post.side_effect = (
        httpx.ReadTimeout("private") if during_backoff else asyncio.CancelledError()
    )
    sleep = AsyncMock(side_effect=asyncio.CancelledError())
    monkeypatch.setattr(source, "_retry_sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await source.WeeklyReportSourceApiClient(
            source.SourceApiSettings("http://source"),
            client=http,
        ).load(REQUEST)
    assert http.post.await_count == 1


@pytest.mark.parametrize("timeout", [0, -1, 121, float("nan"), float("inf")])
def test_timeout_settings_remain_bounded(timeout):
    with pytest.raises(ValueError):
        source.SourceApiSettings("http://source", timeout_seconds=timeout)


def test_json_formatter_keeps_metadata_without_exception_text_or_unapproved_fields():
    record = logging.LogRecord("worker", logging.ERROR, "", 1, "stage_failed", (), None)
    record.job_id = "test-job"
    record.stage = "producer"
    record.error_code = "source_timeout"
    record.secret = "private ward data"
    error = RuntimeError("private exception text")
    error.__cause__ = httpx.ReadTimeout("private URL")
    record.exc_info = (type(error), error, None)
    encoded = JsonDiagnosticFormatter(DIAGNOSTIC_FIELDS).format(record)
    event = json.loads(encoded)
    assert event["stage"] == "producer"
    assert event["job_id"] == "test-job"
    assert event["cause_type"] == "ReadTimeout"
    assert event["timestamp"]
    assert "private" not in encoded

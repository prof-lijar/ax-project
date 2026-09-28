import asyncio
import hashlib
import json
import zipfile
from datetime import date
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from ax_contracts import (
    WeeklyReportBulkJobRequest,
    WeeklyReportRequest,
    WeeklyReportSourceResponse,
)
from ax_persistence import (
    BulkItemRecord,
    BulkStoreError,
    InMemoryBulkJobStore,
    LocalBulkArtifactStore,
)

from apps.workers.weekly_report import WorkerSettings, _serve_jobs
from workflows.weekly_report.bulk import (
    WEEKLY_REPORT_BULK_JOB_KIND,
    WeeklyReportBulkRunner,
    WeeklyReportStorageRecord,
    WeeklyReportStorageUnavailable,
)
from workflows.weekly_report.diagnostics import SOURCE_JOB_ID
from workflows.weekly_report.tools import source_api_client as source_client
from workflows.weekly_report.tools.source_repository import (
    MockWeeklyReportSourceRepository,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("recover", [True, False])
async def test_bulk_source_timeout_retries_in_same_job(tmp_path, monkeypatch, caplog, recover):
    request = WeeklyReportBulkJobRequest(
        week_start=date(2026, 9, 21), max_reports=1,
        idempotency_key="source-timeout-recovery",
    )
    store = InMemoryBulkJobStore()
    job = await store.create_job(
        WEEKLY_REPORT_BULK_JOB_KIND, request.idempotency_key,
        request.model_dump(mode="json"),
    )
    snapshot = await MockWeeklyReportSourceRepository().load(
        WeeklyReportRequest(week_start=request.week_start, limit=1)
    )
    calls = 0
    async def handle(http_request):
        nonlocal calls
        calls += 1
        if not recover or calls == 1:
            raise httpx.ReadTimeout("private data must not be logged")
        return httpx.Response(200, json=snapshot.model_dump(mode="json"))

    # Patch only the client's backoff, not the event-loop sleeps used by the runner.
    monkeypatch.setattr(source_client, "_retry_sleep", AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        source = source_client.WeeklyReportSourceApiClient(
            source_client.SourceApiSettings("http://source"), client=http,
        )
        status = await WeeklyReportBulkRunner(
            store, LocalBulkArtifactStore(tmp_path.resolve(), minimum_free_bytes=0),
            source, FakeModel(), RecordingWeeklyReportStore(), poll_seconds=0.001,
        ).run(job.job_id, concurrency=1)
    assert status.job_id == job.job_id
    assert status.status == ("completed" if recover else "failed")
    assert status.completed_count == (1 if recover else 0)
    assert calls == (2 if recover else 3)
    retries = [r for r in caplog.records if r.msg == "weekly_report_source_retry"]
    assert all(r.job_id == str(job.job_id) for r in retries)
    assert SOURCE_JOB_ID.get() is None
    if not recover:
        failure = next(r for r in caplog.records if r.msg == "weekly report bulk stage failed")
        assert failure.stage == "producer"
        assert failure.error_code == "source_timeout"
        assert failure.cause_type == "ReadTimeout"
        assert failure.attempt == 3


class FakeModel:
    calls = 0

    async def complete(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        self.calls += 1
        assert "<가입자_주간_데이터>" in messages[0]["content"]
        return (
            "지난 한 주 가입자님은 생활 활동과 TV 이용 등 일상적인 생활 패턴을 "
            "함께 살펴봤어요. 집 안 환경과 생활 정보 수신 상태도 확인했고, "
            "생활 흐름을 한 번 더 살펴봐 주세요."
        )


class BlockingModel:
    def __init__(self, expected_calls: int) -> None:
        self.expected_calls = expected_calls
        self.started_calls = 0
        self.cancelled_calls = 0
        self.all_started = asyncio.Event()

    async def complete(self, *args: object, **kwargs: object) -> str:
        self.started_calls += 1
        if self.started_calls == self.expected_calls:
            self.all_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled_calls += 1
            raise
        raise AssertionError("unreachable")


class ConcurrencyTrackingModel:
    def __init__(self) -> None:
        self.active_calls = 0
        self.maximum_active_calls = 0

    async def complete(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        self.active_calls += 1
        self.maximum_active_calls = max(
            self.maximum_active_calls, self.active_calls
        )
        try:
            await asyncio.sleep(0.01)
            return (
                "지난 한 주 가입자님은 생활 활동과 TV 이용 등 일상적인 생활 패턴을 "
                "함께 살펴봤어요. 집 안 환경과 생활 정보 수신 상태도 확인했고, "
                "생활 흐름을 한 번 더 살펴봐 주세요."
            )
        finally:
            self.active_calls -= 1


class BlockingJobRunner:
    def __init__(self, store: InMemoryBulkJobStore) -> None:
        self.store = store
        self.started: list[UUID] = []
        self.active: set[UUID] = set()
        self.maximum_active = 0
        self.two_started = asyncio.Event()
        self.third_started = asyncio.Event()
        self.releases: dict[UUID, asyncio.Event] = {}

    async def run(self, job_id: UUID, *, concurrency: int) -> None:
        del concurrency
        self.started.append(job_id)
        self.active.add(job_id)
        self.maximum_active = max(self.maximum_active, len(self.active))
        self.releases[job_id] = asyncio.Event()
        if len(self.started) >= 2:
            self.two_started.set()
        if len(self.started) >= 3:
            self.third_started.set()
        try:
            await self.releases[job_id].wait()
            await self.store.set_job_status(job_id, "completed")
        finally:
            self.active.discard(job_id)


class FailingThenBlockingJobRunner:
    def __init__(self, failing_job_id: UUID) -> None:
        self.failing_job_id = failing_job_id
        self.started: list[UUID] = []
        self.later_job_started = asyncio.Event()

    async def run(self, job_id: UUID, *, concurrency: int) -> None:
        del concurrency
        self.started.append(job_id)
        if job_id == self.failing_job_id:
            raise RuntimeError("injected runner failure")
        self.later_job_started.set()
        await asyncio.Event().wait()


class EmptyRecordingSource:
    def __init__(self) -> None:
        self.limits: list[int] = []

    async def load(self, request):
        self.limits.append(request.limit)
        return WeeklyReportSourceResponse(
            week_start=request.week_start,
            week_end=request.week_end,
            timezone=request.timezone,
        )


class FailingSource:
    async def load(self, request):
        raise RuntimeError("source unavailable")


class RecordingWeeklyReportStore:
    def __init__(self) -> None:
        self.records: list[WeeklyReportStorageRecord] = []

    async def upsert_reports(self, reports) -> int:
        stored_count = 0
        async for report in reports:
            self.records.append(report)
            stored_count += 1
        return stored_count


class FailingWeeklyReportStore:
    async def upsert_reports(self, reports) -> int:
        async for _ in reports:
            break
        raise WeeklyReportStorageUnavailable("test storage failure")


def test_worker_settings_bound_concurrent_jobs(monkeypatch) -> None:
    monkeypatch.setenv("WEEKLY_REPORT_JOB_DATABASE_DSN", "postgresql://test")
    monkeypatch.delenv("WEEKLY_REPORT_ACTIVE_JOB_LIMIT", raising=False)

    assert WorkerSettings.from_env().active_job_limit == 4

    monkeypatch.setenv("WEEKLY_REPORT_ACTIVE_JOB_LIMIT", "0")
    with pytest.raises(ValueError, match="ACTIVE_JOB_LIMIT"):
        WorkerSettings.from_env()


@pytest.mark.asyncio
async def test_bulk_runner_exports_manifest_jsonl_markdown_and_json(tmp_path) -> None:
    store = InMemoryBulkJobStore()
    artifacts = LocalBulkArtifactStore(tmp_path.resolve(), minimum_free_bytes=0)
    request = WeeklyReportBulkJobRequest(
        week_start=date(2026, 8, 3),
        max_reports=3,
        idempotency_key="weekly-2026-08-03",
    )
    job = await store.create_job(
        WEEKLY_REPORT_BULK_JOB_KIND,
        request.idempotency_key,
        request.model_dump(mode="json"),
    )
    model = FakeModel()
    report_store = RecordingWeeklyReportStore()
    status = await WeeklyReportBulkRunner(
        store,
        artifacts,
        MockWeeklyReportSourceRepository(),
        model,
        report_store,
        poll_seconds=0.001,
    ).run(job.job_id, concurrency=3)

    assert status.status == "completed"
    assert status.completed_count == 3
    assert status.fallback_count == 0
    assert model.calls == 3
    assert [record.ward_id for record in report_store.records] == [101, 102, 103]
    assert all(
        json.loads(record.report_data_json)["template_version"]
        == "weekly-report-v5"
        for record in report_store.records
    )
    assert status.export is not None
    with zipfile.ZipFile(artifacts.local_path(status.export.uri)) as archive:
        assert archive.namelist() == [
            "manifest.json",
            "reports.jsonl",
            "reports/101.md",
            "json/101.json",
            "reports/102.md",
            "json/102.json",
            "reports/103.md",
            "json/103.json",
        ]
        reports_jsonl = archive.read("reports.jsonl")
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["report_count"] == 3
        assert (
            manifest["reports_jsonl_sha256"]
            == hashlib.sha256(reports_jsonl).hexdigest()
        )
        assert "# 주간 생활 리포트" in archive.read("reports/101.md").decode()
        first_report = json.loads(reports_jsonl.splitlines()[0])
        assert first_report["template_data"]["template_version"] == (
            "weekly-report-v5"
        )
        assert first_report["template_data"]["title"] == "주간 생활 리포트"
        assert first_report["markdown"].startswith("# 주간 생활 리포트")
        frontend_report = json.loads(archive.read("json/101.json"))
        assert frontend_report == first_report["template_data"]
        assert "markdown" not in frontend_report


@pytest.mark.asyncio
async def test_bulk_job_submission_is_idempotent() -> None:
    store = InMemoryBulkJobStore()
    request = WeeklyReportBulkJobRequest(
        week_start=date(2026, 8, 3), idempotency_key="same-weekly-job"
    )
    first = await store.create_job(
        WEEKLY_REPORT_BULK_JOB_KIND,
        request.idempotency_key,
        request.model_dump(mode="json"),
    )
    second = await store.create_job(
        WEEKLY_REPORT_BULK_JOB_KIND,
        request.idempotency_key,
        request.model_dump(mode="json"),
    )

    assert first.job_id == second.job_id

    conflicting = request.model_copy(update={"max_reports": 5})
    with pytest.raises(BulkStoreError, match="already used"):
        await store.create_job(
            WEEKLY_REPORT_BULK_JOB_KIND,
            conflicting.idempotency_key,
            conflicting.model_dump(mode="json"),
        )


@pytest.mark.asyncio
async def test_bulk_scheduler_starts_distinct_jobs_without_waiting_for_first() -> None:
    store = InMemoryBulkJobStore()
    jobs = []
    for index in range(3):
        request = WeeklyReportBulkJobRequest(
            week_start=date(2026, 8, 3),
            max_reports=1,
            idempotency_key=f"concurrent-job-{index}",
        )
        jobs.append(
            await store.create_job(
                WEEKLY_REPORT_BULK_JOB_KIND,
                request.idempotency_key,
                request.model_dump(mode="json"),
            )
        )
    runner = BlockingJobRunner(store)
    serving = asyncio.create_task(
        _serve_jobs(
            store,
            runner,
            active_job_limit=2,
            item_concurrency=8,
            poll_seconds=0.001,
        )
    )
    try:
        await asyncio.wait_for(runner.two_started.wait(), timeout=1)
        assert runner.started == [jobs[0].job_id, jobs[1].job_id]
        assert runner.maximum_active == 2

        runner.releases[jobs[0].job_id].set()
        await asyncio.wait_for(runner.third_started.wait(), timeout=1)
        assert runner.started == [
            jobs[0].job_id,
            jobs[1].job_id,
            jobs[2].job_id,
        ]
        assert runner.maximum_active == 2
    finally:
        serving.cancel()
        with pytest.raises(asyncio.CancelledError):
            await serving


@pytest.mark.asyncio
async def test_bulk_scheduler_failure_does_not_block_a_later_job() -> None:
    store = InMemoryBulkJobStore()
    jobs = []
    for index in range(2):
        request = WeeklyReportBulkJobRequest(
            week_start=date(2026, 8, 3),
            max_reports=1,
            idempotency_key=f"scheduler-failure-{index}",
        )
        jobs.append(
            await store.create_job(
                WEEKLY_REPORT_BULK_JOB_KIND,
                request.idempotency_key,
                request.model_dump(mode="json"),
            )
        )
    runner = FailingThenBlockingJobRunner(jobs[0].job_id)
    serving = asyncio.create_task(
        _serve_jobs(
            store,
            runner,
            active_job_limit=1,
            item_concurrency=8,
            poll_seconds=0.01,
        )
    )
    try:
        await asyncio.wait_for(runner.later_job_started.wait(), timeout=1)
        assert runner.started[:2] == [jobs[0].job_id, jobs[1].job_id]
    finally:
        serving.cancel()
        with pytest.raises(asyncio.CancelledError):
            await serving


@pytest.mark.asyncio
async def test_concurrent_jobs_share_one_process_wide_item_limit(tmp_path) -> None:
    store = InMemoryBulkJobStore()
    jobs = []
    for index in range(2):
        request = WeeklyReportBulkJobRequest(
            week_start=date(2026, 8, 3),
            max_reports=1,
            idempotency_key=f"shared-item-limit-{index}",
        )
        jobs.append(
            await store.create_job(
                WEEKLY_REPORT_BULK_JOB_KIND,
                request.idempotency_key,
                request.model_dump(mode="json"),
            )
        )
    model = ConcurrencyTrackingModel()
    runner = WeeklyReportBulkRunner(
        store,
        LocalBulkArtifactStore(tmp_path.resolve(), minimum_free_bytes=0),
        MockWeeklyReportSourceRepository(),
        model,
        RecordingWeeklyReportStore(),
        poll_seconds=0.001,
        item_semaphore=asyncio.Semaphore(1),
    )

    statuses = await asyncio.gather(
        *(runner.run(job.job_id, concurrency=2) for job in jobs)
    )

    assert [status.status for status in statuses] == ["completed", "completed"]
    assert model.maximum_active_calls == 1


@pytest.mark.asyncio
async def test_bulk_runner_requests_one_hundred_wards_per_source_page(
    tmp_path,
) -> None:
    store = InMemoryBulkJobStore()
    artifacts = LocalBulkArtifactStore(tmp_path.resolve(), minimum_free_bytes=0)
    request = WeeklyReportBulkJobRequest(
        week_start=date(2026, 8, 3),
        max_reports=100,
        idempotency_key="weekly-page-size-100",
    )
    job = await store.create_job(
        WEEKLY_REPORT_BULK_JOB_KIND,
        request.idempotency_key,
        request.model_dump(mode="json"),
    )
    source = EmptyRecordingSource()

    status = await WeeklyReportBulkRunner(
        store,
        artifacts,
        source,
        FakeModel(),
        RecordingWeeklyReportStore(),
        poll_seconds=0.001,
    ).run(job.job_id, concurrency=1)

    assert status.status == "completed"
    assert source.limits == [100]


@pytest.mark.asyncio
async def test_bulk_runner_marks_producer_failure_terminal(tmp_path) -> None:
    store = InMemoryBulkJobStore()
    artifacts = LocalBulkArtifactStore(tmp_path.resolve(), minimum_free_bytes=0)
    request = WeeklyReportBulkJobRequest(
        week_start=date(2026, 8, 3),
        max_reports=1,
        idempotency_key="producer-failure-is-terminal",
    )
    job = await store.create_job(
        WEEKLY_REPORT_BULK_JOB_KIND,
        request.idempotency_key,
        request.model_dump(mode="json"),
    )

    status = await WeeklyReportBulkRunner(
        store,
        artifacts,
        FailingSource(),
        FakeModel(),
        RecordingWeeklyReportStore(),
        poll_seconds=0.001,
    ).run(job.job_id, concurrency=1)

    assert status.status == "failed"
    assert status.running_count == 0
    assert status.pending_count == 0


@pytest.mark.asyncio
async def test_bulk_runner_does_not_complete_when_report_storage_fails(
    tmp_path,
) -> None:
    store = InMemoryBulkJobStore()
    artifacts = LocalBulkArtifactStore(tmp_path.resolve(), minimum_free_bytes=0)
    request = WeeklyReportBulkJobRequest(
        week_start=date(2026, 8, 3),
        max_reports=1,
        idempotency_key="report-storage-failure-is-terminal",
    )
    job = await store.create_job(
        WEEKLY_REPORT_BULK_JOB_KIND,
        request.idempotency_key,
        request.model_dump(mode="json"),
    )

    status = await WeeklyReportBulkRunner(
        store,
        artifacts,
        MockWeeklyReportSourceRepository(),
        FakeModel(),
        FailingWeeklyReportStore(),
        poll_seconds=0.001,
    ).run(job.job_id, concurrency=1)

    assert status.status == "failed"
    assert status.completed_count == 1
    assert status.export is None


@pytest.mark.asyncio
async def test_export_only_job_completes_without_calling_report_storage(tmp_path) -> None:
    store = InMemoryBulkJobStore()
    artifacts = LocalBulkArtifactStore(tmp_path.resolve(), minimum_free_bytes=0)
    request = WeeklyReportBulkJobRequest(
        week_start=date(2026, 8, 3),
        max_reports=1,
        idempotency_key="ui-export-only-job",
        persist_reports=False,
    )
    job = await store.create_job(
        WEEKLY_REPORT_BULK_JOB_KIND,
        request.idempotency_key,
        request.model_dump(mode="json"),
    )
    status = await WeeklyReportBulkRunner(
        store,
        artifacts,
        MockWeeklyReportSourceRepository(),
        FakeModel(),
        FailingWeeklyReportStore(),
        poll_seconds=0.001,
    ).run(job.job_id, concurrency=1)

    assert status.status == "completed"
    assert status.completed_count == 1
    assert status.export is not None
    with zipfile.ZipFile(artifacts.local_path(status.export.uri)) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["request"]["persist_reports"] is False
        assert len(archive.read("reports.jsonl").splitlines()) == 1
        names = archive.namelist()
        assert len([name for name in names if name.startswith("reports/")]) == 1
        assert len([name for name in names if name.startswith("json/")]) == 1


@pytest.mark.asyncio
async def test_bulk_runner_falls_back_when_one_model_item_times_out(tmp_path) -> None:
    store = InMemoryBulkJobStore()
    artifacts = LocalBulkArtifactStore(tmp_path.resolve(), minimum_free_bytes=0)
    request = WeeklyReportBulkJobRequest(
        week_start=date(2026, 8, 3),
        max_reports=1,
        idempotency_key="model-item-timeout-fallback",
    )
    job = await store.create_job(
        WEEKLY_REPORT_BULK_JOB_KIND,
        request.idempotency_key,
        request.model_dump(mode="json"),
    )
    model = BlockingModel(expected_calls=1)

    status = await WeeklyReportBulkRunner(
        store,
        artifacts,
        MockWeeklyReportSourceRepository(),
        model,
        RecordingWeeklyReportStore(),
        poll_seconds=0.001,
        item_timeout_seconds=0.01,
    ).run(job.job_id, concurrency=1)

    assert status.status == "completed"
    assert status.completed_count == 1
    assert status.fallback_count == 1
    assert model.cancelled_calls == 1


@pytest.mark.asyncio
async def test_recent_bulk_jobs_are_newest_first_and_bounded() -> None:
    store = InMemoryBulkJobStore()
    requests = [
        WeeklyReportBulkJobRequest(
            week_start=date(2026, 8, 3), idempotency_key=f"weekly-job-{index}"
        )
        for index in range(3)
    ]
    jobs = [
        await store.create_job(
            WEEKLY_REPORT_BULK_JOB_KIND,
            request.idempotency_key,
            request.model_dump(mode="json"),
        )
        for request in requests
    ]

    recent = await store.list_jobs(WEEKLY_REPORT_BULK_JOB_KIND, limit=2)

    assert [job.job_id for job in recent] == [jobs[2].job_id, jobs[1].job_id]
    with pytest.raises(ValueError, match="between 1 and 100"):
        await store.list_jobs(WEEKLY_REPORT_BULK_JOB_KIND, limit=101)


@pytest.mark.asyncio
async def test_cancelled_items_are_terminal() -> None:
    store = InMemoryBulkJobStore()
    request = WeeklyReportBulkJobRequest(
        week_start=date(2026, 8, 3), idempotency_key="cancel-weekly-job"
    )
    job = await store.create_job(
        WEEKLY_REPORT_BULK_JOB_KIND,
        request.idempotency_key,
        request.model_dump(mode="json"),
    )
    await store.request_cancel(job.job_id)
    await store.cancel_pending_items(job.job_id)

    assert (await store.get_job(job.job_id)).status == "cancelling"


@pytest.mark.asyncio
async def test_bulk_runner_cancels_in_flight_report_generation(tmp_path) -> None:
    store = InMemoryBulkJobStore()
    artifacts = LocalBulkArtifactStore(tmp_path.resolve(), minimum_free_bytes=0)
    request = WeeklyReportBulkJobRequest(
        week_start=date(2026, 8, 3),
        max_reports=3,
        idempotency_key="cancel-running-weekly-job",
    )
    job = await store.create_job(
        WEEKLY_REPORT_BULK_JOB_KIND,
        request.idempotency_key,
        request.model_dump(mode="json"),
    )
    model = BlockingModel(expected_calls=3)
    running = asyncio.create_task(
        WeeklyReportBulkRunner(
            store,
            artifacts,
            MockWeeklyReportSourceRepository(),
            model,
            RecordingWeeklyReportStore(),
            poll_seconds=0.001,
        ).run(job.job_id, concurrency=3)
    )

    await asyncio.wait_for(model.all_started.wait(), timeout=1)
    await store.request_cancel(job.job_id)
    status = await asyncio.wait_for(running, timeout=5)

    assert status.status == "cancelled"
    assert status.completed_count == 0
    assert status.failed_count == 3
    assert model.cancelled_calls == 3
    assert not (tmp_path / str(job.job_id) / "reports").exists()


@pytest.mark.asyncio
async def test_item_becomes_failed_after_three_leased_attempts() -> None:
    store = InMemoryBulkJobStore()
    request = WeeklyReportBulkJobRequest(
        week_start=date(2026, 8, 3), idempotency_key="retry-weekly-job"
    )
    job = await store.create_job(
        WEEKLY_REPORT_BULK_JOB_KIND,
        request.idempotency_key,
        request.model_dump(mode="json"),
    )
    await store.stage_items(
        job.job_id,
        [BulkItemRecord(job.job_id, "0001", "file:///input", "checksum")],
        None,
    )
    for attempt in range(3):
        owner = f"worker-{attempt}"
        item = (await store.claim_items(job.job_id, owner, 1, 30))[0]
        await store.fail_item(
            job.job_id, item.item_key, owner, "invalid_contract", max_attempts=3
        )

    items = await store.list_items(job.job_id)
    assert items[0].status == "failed"
    assert items[0].attempt_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [False, True])
async def test_selected_wards_generate_only_requested_reports_without_storage(tmp_path, missing):
    class SelectedSource(MockWeeklyReportSourceRepository):
        def __init__(self):
            self.requests = []

        async def load(self, request):
            self.requests.append(request)
            response = await super().load(request)
            if missing:
                return response.model_copy(update={
                    "items": [item for item in response.items if item.ward_id != 45],
                })
            return response

    store = InMemoryBulkJobStore()
    artifacts = LocalBulkArtifactStore(tmp_path.resolve(), minimum_free_bytes=0)
    request = WeeklyReportBulkJobRequest(
        week_start=date(2026, 8, 3), ward_ids=[56, 23, 45],
        persist_reports=False, idempotency_key="selected-ward-test",
    )
    job = await store.create_job(
        WEEKLY_REPORT_BULK_JOB_KIND, request.idempotency_key,
        request.model_dump(mode="json"),
    )
    source = SelectedSource()
    status = await WeeklyReportBulkRunner(
        store, artifacts, source, FakeModel(), FailingWeeklyReportStore(),
        poll_seconds=0.001,
    ).run(job.job_id, concurrency=1)

    assert status.status == ("failed" if missing else "completed")
    assert status.max_reports == 3
    assert status.completed_count == (0 if missing else 3)
    assert len(source.requests) == 1
    assert source.requests[0].ward_ids == [23, 45, 56]
    assert source.requests[0].cursor is None
    assert status.next_cursor is None
    assert status.selection_truncated is False
    if missing:
        assert status.export is None
        return
    assert status.export is not None
    with zipfile.ZipFile(artifacts.local_path(status.export.uri)) as archive:
        ids = {json.loads(line)["ward_id"] for line in archive.read("reports.jsonl").splitlines()}
        assert ids == ({23, 56} if missing else {23, 45, 56})
        assert json.loads(archive.read("manifest.json"))["request"]["persist_reports"] is False


@pytest.mark.asyncio
async def test_selected_wards_reject_unrequested_source_items(tmp_path):
    class WrongSource(MockWeeklyReportSourceRepository):
        async def load(self, request):
            return await super().load(request.model_copy(update={"ward_ids": [101]}))

    store = InMemoryBulkJobStore()
    artifacts = LocalBulkArtifactStore(tmp_path.resolve(), minimum_free_bytes=0)
    request = WeeklyReportBulkJobRequest(
        week_start=date(2026, 8, 3), ward_ids=[23],
        persist_reports=False, idempotency_key="wrong-selected-ward",
    )
    job = await store.create_job(
        WEEKLY_REPORT_BULK_JOB_KIND, request.idempotency_key,
        request.model_dump(mode="json"),
    )
    status = await WeeklyReportBulkRunner(
        store, artifacts, WrongSource(), FakeModel(), FailingWeeklyReportStore(),
        poll_seconds=0.001,
    ).run(job.job_id, concurrency=1)
    assert status.status == "failed"
    assert status.discovered_count == 0
    assert status.export is None


@pytest.mark.asyncio
async def test_selected_wards_resume_after_a_partially_staged_selection(tmp_path):
    requests = []

    class RecordingSource(MockWeeklyReportSourceRepository):
        async def load(self, request):
            requests.append(request)
            return await super().load(request)

    store = InMemoryBulkJobStore()
    artifacts = LocalBulkArtifactStore(tmp_path.resolve(), minimum_free_bytes=0)
    request = WeeklyReportBulkJobRequest(
        week_start=date(2026, 8, 3), ward_ids=[23, 45, 56],
        persist_reports=False, idempotency_key="resume-selected-wards",
    )
    job = await store.create_job(
        WEEKLY_REPORT_BULK_JOB_KIND, request.idempotency_key,
        request.model_dump(mode="json"),
    )
    source = await MockWeeklyReportSourceRepository().load(WeeklyReportRequest(
        week_start=request.week_start, ward_ids=[23],
    ))
    artifact = artifacts.write_json(
        job.job_id, "inputs/23.json", source.items[0].model_dump(mode="json"),
    )
    await store.stage_items(job.job_id, [BulkItemRecord(
        job_id=job.job_id, item_key=f"{23:020d}",
        payload_uri=artifact.uri, payload_checksum=artifact.sha256,
    )], None)
    status = await WeeklyReportBulkRunner(
        store, artifacts, RecordingSource(), FakeModel(), FailingWeeklyReportStore(),
        poll_seconds=0.001,
    ).run(job.job_id, concurrency=1)
    assert status.status == "completed"
    assert status.completed_count == 3
    assert len(requests) == 1
    assert requests[0].ward_ids == [45, 56]
    assert {int(item.item_key) for item in await store.list_items(job.job_id)} == {23, 45, 56}


@pytest.mark.asyncio
async def test_every_ward_is_stored_even_without_data_or_a_working_model(tmp_path):
    from workflows.weekly_report.source.queries import CANDIDATE_WARDS_SQL
    from workflows.weekly_report.source.service import WeeklyReportSourceService

    class Database:
        async def fetch(self, query, *args):
            if query == CANDIDATE_WARDS_SQL:
                after, limit = args
                return [{"ward_id": ward, "full_name": f"대상 {ward}"}
                        for ward in range(1, 104) if ward > after][:limit]
            return []

    class Source:
        async def load(self, request):
            return await WeeklyReportSourceService(Database()).build(request)

    class BrokenModel:
        async def complete(self, *args, **kwargs):
            raise RuntimeError("unexpected model adapter failure")

    store = InMemoryBulkJobStore()
    artifacts = LocalBulkArtifactStore(tmp_path.resolve(), minimum_free_bytes=0)
    request = WeeklyReportBulkJobRequest(
        week_start=date(2026, 9, 14), idempotency_key="all-wards-no-weekly-data",
    )
    job = await store.create_job(
        WEEKLY_REPORT_BULK_JOB_KIND, request.idempotency_key,
        request.model_dump(mode="json"),
    )
    report_store = RecordingWeeklyReportStore()
    status = await WeeklyReportBulkRunner(
        store, artifacts, Source(), BrokenModel(), report_store, poll_seconds=0.001,
    ).run(job.job_id, concurrency=4)

    assert status.status == "completed"
    assert status.discovered_count == status.completed_count == status.fallback_count == 103
    assert status.failed_count == 0
    assert {record.ward_id for record in report_store.records} == set(range(1, 104))
    for record in report_store.records:
        template = json.loads(record.report_data_json)
        assert template["generation_notice"] is None
        assert template["basic_info"]["risk_score"] is None
        assert template["device_status"]["metrics"]["normal_reception_days"] == 0
    with zipfile.ZipFile(artifacts.local_path(status.export.uri)) as archive:
        assert len([name for name in archive.namelist() if name.startswith("json/")]) == 103


@pytest.mark.asyncio
async def test_failed_report_cannot_commit_a_smaller_batch(tmp_path, monkeypatch):
    store = InMemoryBulkJobStore()
    artifacts = LocalBulkArtifactStore(tmp_path.resolve(), minimum_free_bytes=0)
    original_write = artifacts.write_json

    def fail_one_report(job_id, name, payload):
        if name == "reports/102.json":
            raise OSError("injected artifact write failure")
        return original_write(job_id, name, payload)

    monkeypatch.setattr(artifacts, "write_json", fail_one_report)
    request = WeeklyReportBulkJobRequest(
        week_start=date(2026, 9, 14), max_reports=3, idempotency_key="no-partial-storage",
    )
    job = await store.create_job(
        WEEKLY_REPORT_BULK_JOB_KIND, request.idempotency_key,
        request.model_dump(mode="json"),
    )
    report_store = RecordingWeeklyReportStore()
    status = await WeeklyReportBulkRunner(
        store, artifacts, MockWeeklyReportSourceRepository(), FakeModel(),
        report_store, poll_seconds=0.001,
    ).run(job.job_id, concurrency=3)

    assert status.status == "failed"
    assert status.completed_count == 2
    assert status.failed_count == 1
    assert status.export is None
    assert report_store.records == []

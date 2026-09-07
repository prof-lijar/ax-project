import json
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from app import scheduler_service as legacy_scheduler_service
from app.scout_api_client import (
    ScoutApiCallError,
    ScoutApiClient,
    ScoutRunFailedResponse,
)
from app.scout_schedule_models import (
    ScoutRunFailure,
    ScoutRunSuccess,
    ScoutScheduleCreateRequest,
    ScoutScheduleRecurrence,
    ScoutScheduleStatus,
)
from app.scout_schedule_repository import ScheduleTransitionError
from app.scout_schedule_service import (
    ScoutScheduleService,
    ScoutScheduleSettings,
    _build_recurring_trigger,
)

SEOUL = ZoneInfo("Asia/Seoul")


def schedule_request(
    *, seconds: float = 30, suffix: str = "one"
) -> ScoutScheduleCreateRequest:
    run_at = (datetime.now(SEOUL) + timedelta(seconds=seconds)).replace(
        tzinfo=None, microsecond=0
    )
    return ScoutScheduleCreateRequest(
        topic=f"Scout topic {suffix}",
        keywords=["AI", "IoT"],
        additional_instructions="Focus on public-sector cases.",
        run_at=run_at.isoformat(),
        timezone="Asia/Seoul",
    )


def recurring_request(
    recurrence: str = "daily",
    *,
    suffix: str = "recurring",
) -> ScoutScheduleCreateRequest:
    fields: dict[str, object] = {}
    if recurrence == "weekly":
        fields["day_of_week"] = "wednesday"
    elif recurrence == "monthly":
        fields["day_of_month"] = 31
    return ScoutScheduleCreateRequest(
        topic=f"Scout topic {suffix}",
        keywords=["AI", "IoT"],
        additional_instructions="Only prioritize recent sources.",
        recurrence=recurrence,
        schedule_time="09:30:00",
        timezone="Asia/Seoul",
        **fields,
    )


def success_result() -> ScoutRunSuccess:
    started = datetime.now(UTC)
    return ScoutRunSuccess(
        run_id="run-success",
        status="success",
        started_at=started,
        completed_at=started + timedelta(seconds=62),
        duration_seconds=61.432,
        source_count=1,
        report="# Scout Report\n\n## Topic\n\nTest",
        sources=["https://example.com/evidence"],
        report_artifact="runs/run-success/report.md",
        log_artifact="runs/run-success/execution.jsonl",
    )


def failure_result() -> ScoutRunFailure:
    started = datetime.now(UTC)
    return ScoutRunFailure(
        run_id="run-failed",
        status="failed",
        started_at=started,
        completed_at=started + timedelta(seconds=4),
        duration_seconds=3.75,
        source_count=0,
        log_artifact="runs/run-failed/execution.jsonl",
    )


class FakeScoutClient:
    def __init__(
        self,
        result: ScoutRunSuccess | None = None,
        error: Exception | None = None,
        delay: float = 0,
    ) -> None:
        self.result = result or success_result()
        self.error = error
        self.delay = delay
        self.calls: list[tuple[str, list[str], str | None]] = []
        self.closed = False
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def run_scout(
        self,
        topic: str,
        keywords: list[str],
        additional_instructions: str | None = None,
    ) -> ScoutRunSuccess:
        self.calls.append((topic, keywords, additional_instructions))
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                time.sleep(self.delay)
            if self.error is not None:
                raise self.error
            return self.result
        finally:
            with self._lock:
                self.active -= 1

    def close(self) -> None:
        self.closed = True


def make_service(
    tmp_path: Path,
    client: FakeScoutClient | None = None,
    *,
    concurrency: int = 1,
) -> ScoutScheduleService:
    settings = ScoutScheduleSettings(
        database_path=tmp_path / "schedules.sqlite3",
        concurrency_limit=concurrency,
        misfire_grace_seconds=10,
    )
    scheduler = BackgroundScheduler(
        executors={"default": ThreadPoolExecutor(max_workers=concurrency)},
        timezone=UTC,
    )
    return ScoutScheduleService(
        settings,
        scout_client=client or FakeScoutClient(),
        scheduler=scheduler,
    )


def test_importing_legacy_scheduler_service_does_not_start_threads() -> None:
    assert legacy_scheduler_service.scheduler.running is False


def test_registers_unique_date_trigger_jobs_without_replacement(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    first = service.create_schedule(schedule_request(suffix="first"))
    second = service.create_schedule(schedule_request(suffix="second"))

    jobs = service.scheduler.get_jobs()
    assert {job.id for job in jobs} == {str(first.schedule_id), str(second.schedule_id)}
    assert all(isinstance(job.trigger, DateTrigger) for job in jobs)


@pytest.mark.parametrize("recurrence", ["daily", "weekly", "monthly"])
def test_registers_cron_trigger_for_recurring_rules(
    tmp_path: Path, recurrence: str
) -> None:
    service = make_service(tmp_path)

    created = service.create_schedule(recurring_request(recurrence))
    job = service.scheduler.get_job(str(created.schedule_id))

    assert created.recurrence.value == recurrence
    assert job is not None
    assert isinstance(job.trigger, CronTrigger)
    assert str(job.trigger.timezone) == "Asia/Seoul"


def test_monthly_day_skips_months_without_that_day() -> None:
    trigger = _build_recurring_trigger(
        ScoutScheduleRecurrence.MONTHLY,
        schedule_time=datetime.strptime("09:30:00", "%H:%M:%S").time(),
        day_of_week=None,
        day_of_month=31,
    )

    next_fire = trigger.get_next_fire_time(
        None,
        datetime(2026, 9, 1, tzinfo=SEOUL),
    )

    assert next_fire == datetime(2026, 10, 31, 9, 30, tzinfo=SEOUL)


def test_callback_invokes_scout_contract_once_and_copies_success(
    tmp_path: Path,
) -> None:
    result = success_result()
    client = FakeScoutClient(result=result)
    service = make_service(tmp_path, client)
    created = service.create_schedule(schedule_request())

    service.execute_schedule(created.schedule_id)
    service.execute_schedule(created.schedule_id)

    stored = service.repository.get(created.schedule_id)
    assert client.calls == [
        (created.topic, created.keywords, created.additional_instructions)
    ]
    assert stored.status is ScoutScheduleStatus.SUCCEEDED
    assert stored.scout_run == result


def test_recurring_success_remains_active_and_runs_again(tmp_path: Path) -> None:
    result = success_result()
    client = FakeScoutClient(result=result)
    service = make_service(tmp_path, client)
    created = service.create_schedule(recurring_request())
    first_trigger = created.trigger_at

    service.execute_schedule(created.schedule_id)
    after_first = service.repository.get(created.schedule_id)
    service.execute_schedule(created.schedule_id)
    after_second = service.repository.get(created.schedule_id)

    assert client.calls == [
        (created.topic, created.keywords, created.additional_instructions),
        (created.topic, created.keywords, created.additional_instructions),
    ]
    assert after_first.status is ScoutScheduleStatus.PENDING
    assert after_first.scout_run == result
    assert after_first.trigger_at > first_trigger
    assert after_second.status is ScoutScheduleStatus.PENDING
    assert after_second.trigger_at > after_first.trigger_at


def test_recurring_transport_failure_remains_active(tmp_path: Path) -> None:
    client = FakeScoutClient(
        error=ScoutApiCallError("scout_unreachable", "Scout was unreachable.")
    )
    service = make_service(tmp_path, client)
    created = service.create_schedule(recurring_request())

    service.execute_schedule(created.schedule_id)

    stored = service.repository.get(created.schedule_id)
    assert stored.status is ScoutScheduleStatus.PENDING
    assert stored.error_code == "scout_unreachable"
    assert stored.trigger_at > created.trigger_at


def test_calculator_worker_workflow_is_never_invoked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden_worker_call(*args: object, **kwargs: object) -> None:
        raise AssertionError("calculator Worker Agent must not be called")

    monkeypatch.setattr(
        legacy_scheduler_service,
        "run_worker_agent_workflow",
        forbidden_worker_call,
    )
    service = make_service(tmp_path)
    created = service.create_schedule(schedule_request())

    service.execute_schedule(created.schedule_id)

    assert (
        service.repository.get(created.schedule_id).status
        is ScoutScheduleStatus.SUCCEEDED
    )


def test_failed_scout_502_metadata_is_stored_unchanged(tmp_path: Path) -> None:
    failed_run = failure_result()
    client = FakeScoutClient(error=ScoutRunFailedResponse(failed_run))
    service = make_service(tmp_path, client)
    created = service.create_schedule(schedule_request())

    service.execute_schedule(created.schedule_id)

    stored = service.repository.get(created.schedule_id)
    assert stored.status is ScoutScheduleStatus.FAILED
    assert stored.error_code == "scout_run_failed"
    assert stored.scout_run == failed_run


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("scout_preflight_failed", "Scout was not ready."),
        ("scout_timeout", "Scout timed out."),
        ("scout_unreachable", "Scout was unreachable."),
    ],
)
def test_preflight_and_transport_failures_do_not_fabricate_scout_timing(
    tmp_path: Path, code: str, message: str
) -> None:
    client = FakeScoutClient(error=ScoutApiCallError(code, message))
    service = make_service(tmp_path, client)
    created = service.create_schedule(schedule_request())

    service.execute_schedule(created.schedule_id)

    stored = service.repository.get(created.schedule_id)
    assert stored.status is ScoutScheduleStatus.FAILED
    assert stored.error_code == code
    assert stored.error_message == message
    assert stored.scout_run is None


def test_unexpected_callback_failure_is_bounded_and_safe(tmp_path: Path) -> None:
    client = FakeScoutClient(error=RuntimeError("sensitive internal detail"))
    service = make_service(tmp_path, client)
    created = service.create_schedule(schedule_request())

    service.execute_schedule(created.schedule_id)

    stored = service.repository.get(created.schedule_id)
    assert stored.status is ScoutScheduleStatus.FAILED
    assert stored.error_code == "schedule_callback_failed"
    assert stored.error_message == "The scheduled Scout callback failed."
    assert "sensitive" not in stored.error_message
    assert stored.scout_run is None


def test_only_pending_schedule_can_be_cancelled(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    pending = service.create_schedule(schedule_request(suffix="pending"))
    cancelled = service.cancel_schedule(pending.schedule_id)

    assert cancelled.status is ScoutScheduleStatus.CANCELLED
    assert service.scheduler.get_job(str(pending.schedule_id)) is None
    with pytest.raises(ScheduleTransitionError):
        service.cancel_schedule(pending.schedule_id)


def test_missed_schedule_is_not_dispatched(tmp_path: Path) -> None:
    client = FakeScoutClient()
    service = make_service(tmp_path, client)
    record = service.repository.create(schedule_request(seconds=30))
    reconciliation_time = record.trigger_at + timedelta(
        seconds=service.settings.misfire_grace_seconds + 1
    )

    service._reconcile_pending_jobs(now=reconciliation_time)

    stored = service.repository.get(record.schedule_id)
    assert stored.status is ScoutScheduleStatus.MISSED
    assert stored.scout_run is None
    assert client.calls == []


def test_restart_reloads_pending_job_without_duplicates(tmp_path: Path) -> None:
    settings = ScoutScheduleSettings(
        database_path=tmp_path / "persistent.sqlite3",
        misfire_grace_seconds=10,
    )
    first_client = FakeScoutClient()
    first = ScoutScheduleService(settings, scout_client=first_client)
    first.start()
    created = first.create_schedule(schedule_request(seconds=60))
    first.shutdown()

    second_client = FakeScoutClient()
    second = ScoutScheduleService(settings, scout_client=second_client)
    try:
        second.start()
        jobs = second.scheduler.get_jobs()
        assert [job.id for job in jobs] == [str(created.schedule_id)]
    finally:
        second.shutdown()


def test_restart_reloads_recurring_cron_job_without_duplicates(tmp_path: Path) -> None:
    settings = ScoutScheduleSettings(
        database_path=tmp_path / "persistent-recurring.sqlite3",
        misfire_grace_seconds=10,
    )
    first = ScoutScheduleService(settings, scout_client=FakeScoutClient())
    first.start()
    created = first.create_schedule(recurring_request("weekly"))
    first.shutdown()

    second = ScoutScheduleService(settings, scout_client=FakeScoutClient())
    try:
        second.start()
        jobs = second.scheduler.get_jobs()
        assert [job.id for job in jobs] == [str(created.schedule_id)]
        assert isinstance(jobs[0].trigger, CronTrigger)
    finally:
        second.shutdown()


def test_expired_recurring_occurrence_advances_instead_of_terminating(
    tmp_path: Path,
) -> None:
    service = make_service(tmp_path)
    old_trigger = datetime.now(UTC) - timedelta(days=2)
    record = service.repository.create(
        recurring_request(),
        trigger_at=old_trigger,
    )

    service._reconcile_pending_jobs(now=datetime.now(UTC))

    stored = service.repository.get(record.schedule_id)
    assert stored.status is ScoutScheduleStatus.PENDING
    assert stored.error_code == "schedule_missed"
    assert stored.trigger_at > datetime.now(UTC)
    assert isinstance(
        service.scheduler.get_job(str(record.schedule_id)).trigger,
        CronTrigger,
    )


def test_service_start_recovers_stale_running_without_retry(tmp_path: Path) -> None:
    client = FakeScoutClient()
    service = make_service(tmp_path, client)
    created = service.repository.create(schedule_request(seconds=60))
    service.repository.claim_pending(created.schedule_id)

    try:
        service.start()
        recovered = service.repository.get(created.schedule_id)
        assert recovered.status is ScoutScheduleStatus.FAILED
        assert recovered.error_code == "stale_running_recovery"
        assert recovered.scout_run is None
        assert client.calls == []
    finally:
        service.shutdown()


def test_service_start_advances_stale_recurring_without_retry(tmp_path: Path) -> None:
    client = FakeScoutClient()
    service = make_service(tmp_path, client)
    created = service.repository.create(
        recurring_request(),
        trigger_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    service.repository.claim_pending(created.schedule_id)

    try:
        service.start()
        recovered = service.repository.get(created.schedule_id)
        assert recovered.status is ScoutScheduleStatus.PENDING
        assert recovered.error_code == "stale_running_recovery"
        assert recovered.trigger_at > datetime.now(UTC)
        assert client.calls == []
    finally:
        service.shutdown()


def test_configured_global_concurrency_limit_queues_due_schedules(
    tmp_path: Path,
) -> None:
    client = FakeScoutClient(delay=0.2)
    service = make_service(tmp_path, client, concurrency=1)
    first = service.repository.create(schedule_request(seconds=1.5, suffix="first"))
    second = service.repository.create(schedule_request(seconds=1.5, suffix="second"))

    service.start()
    try:
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            records = [
                service.repository.get(first.schedule_id),
                service.repository.get(second.schedule_id),
            ]
            if all(
                record.status is ScoutScheduleStatus.SUCCEEDED for record in records
            ):
                break
            time.sleep(0.05)
        assert all(
            service.repository.get(identifier).status is ScoutScheduleStatus.SUCCEEDED
            for identifier in (first.schedule_id, second.schedule_id)
        )
        assert client.max_active == 1
    finally:
        service.shutdown()


def test_scout_api_client_posts_exact_contract_and_preserves_metadata() -> None:
    expected = success_result()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=json.loads(expected.model_dump_json()))

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ScoutApiClient("http://scout.test/", client=http_client)

    actual = client.run_scout(
        "A topic",
        ["one", "two"],
        "  Organize findings by competitor.  ",
    )

    assert actual == expected
    assert requests[0].url == "http://scout.test/v1/scout/runs"
    assert json.loads(requests[0].content) == {
        "topic": "A topic",
        "keywords": ["one", "two"],
        "additional_instructions": "Organize findings by competitor.",
    }


def test_scout_api_client_omits_blank_additional_instructions() -> None:
    expected = success_result()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=json.loads(expected.model_dump_json()))

    client = ScoutApiClient(
        "http://scout.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    client.run_scout("A topic", [], "  ")

    assert json.loads(requests[0].content) == {"topic": "A topic", "keywords": []}


def test_scout_api_client_preserves_safe_502_run_metadata() -> None:
    failed = failure_result()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502,
            json={
                "detail": "Scout run failed.",
                "run": json.loads(failed.model_dump_json()),
            },
        )

    client = ScoutApiClient(
        "http://scout.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ScoutRunFailedResponse) as exc_info:
        client.run_scout("A topic", [])

    assert exc_info.value.run == failed


@pytest.mark.parametrize(
    ("transport_error", "expected_code"),
    [
        (httpx.ReadTimeout("timeout"), "scout_timeout"),
        (httpx.ConnectError("unreachable"), "scout_unreachable"),
    ],
)
def test_scout_api_client_maps_transport_errors_safely(
    transport_error: Exception, expected_code: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise transport_error

    client = ScoutApiClient(
        "http://scout.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ScoutApiCallError) as exc_info:
        client.run_scout("A topic", [])

    assert exc_info.value.code == expected_code
    assert "timeout" not in exc_info.value.safe_message.lower() or (
        expected_code == "scout_timeout"
    )

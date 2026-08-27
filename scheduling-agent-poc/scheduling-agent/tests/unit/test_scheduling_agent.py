import json
import runpy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from google.adk.agents import Agent
from pydantic import ValidationError

from app import agent as agent_module
from app import scheduler_service
from app import worker_agent as worker_agent_module


class StubSessionService:
    async def create_session(
        self, *, app_name: str, user_id: str, session_id: str
    ) -> SimpleNamespace:
        return SimpleNamespace(id=session_id)


class StubRunner:
    def __init__(
        self,
        request_data: dict[str, object],
        output_key: str = agent_module.SCHEDULE_REQUEST_KEY,
    ) -> None:
        self.request_data = request_data
        self.output_key = output_key
        self.session_service = StubSessionService()
        self.messages: list[str] = []

    async def run_async(self, *, new_message: object, **_: object):
        self.messages.append(new_message.parts[0].text)
        yield SimpleNamespace(
            actions=SimpleNamespace(
                state_delta={self.output_key: self.request_data}
            )
        )


def valid_worker_result_data() -> dict[str, object]:
    return {
        "implementation_description": "Implement four pure calculator functions.",
        "required_operations": ["add", "subtract", "multiply", "divide"],
        "test_plan": [
            "Verify add(2, 3) returns 5.",
            "Verify subtract(10, 4) returns 6.",
            "Verify multiply(3, 7) returns 21.",
            "Verify divide(10, 2) returns 5.",
            "Verify division by zero raises ValueError.",
        ],
        "readme_summary": "Document operations, usage, and zero division.",
    }


@pytest.fixture(autouse=True)
def no_scheduler_jobs_remain():
    scheduler_service.scheduler.remove_all_jobs()
    yield
    scheduler_service.scheduler.remove_all_jobs()
    assert scheduler_service.scheduler.get_jobs() == []


def test_schedule_request_extracts_task_a_and_five_seconds() -> None:
    request = agent_module.ScheduleRequest(
        schedule_type="interval", task_name="A", seconds=5
    )

    assert request.schedule_type == "interval"
    assert request.task_name == "A"
    assert request.seconds == 5


def test_schedule_request_rejects_invalid_task_name() -> None:
    with pytest.raises(ValidationError):
        agent_module.ScheduleRequest(
            schedule_type="interval", task_name="D", seconds=5
        )


@pytest.mark.parametrize("seconds", [0, -1])
def test_schedule_request_rejects_non_positive_interval(seconds: int) -> None:
    with pytest.raises(ValidationError):
        agent_module.ScheduleRequest(
            schedule_type="interval", task_name="A", seconds=seconds
        )


def test_schedule_request_accepts_calculator_date_in_seoul() -> None:
    run_at = datetime(2026, 8, 27, 3, 28)

    request = agent_module.ScheduleRequest(
        schedule_type="date",
        workflow_name="calculator",
        run_at=run_at,
        timezone="Asia/Seoul",
    )

    assert request.schedule_type == "date"
    assert request.workflow_name == "calculator"
    assert request.run_at == run_at
    assert request.timezone == "Asia/Seoul"


def test_date_request_treats_run_at_as_seoul_local_wall_time() -> None:
    request = agent_module.ScheduleRequest(
        schedule_type="date",
        workflow_name="calculator",
        run_at=datetime(2026, 8, 27, 3, 28, tzinfo=timezone.utc),
        timezone="Asia/Seoul",
    )

    assert request.run_at == datetime(2026, 8, 27, 3, 28)
    assert request.run_at.tzinfo is None


def test_schedule_request_rejects_incomplete_date_request() -> None:
    with pytest.raises(ValidationError):
        agent_module.ScheduleRequest(
            schedule_type="date",
            workflow_name="calculator",
            run_at=datetime(2026, 8, 27, 3, 28),
        )


def test_schedule_request_accepts_worker_agent_date_in_seoul() -> None:
    run_at = datetime(2026, 8, 27, 10, 10)

    request = agent_module.ScheduleRequest(
        schedule_type="date",
        workflow_name="worker_agent",
        run_at=run_at,
        timezone="Asia/Seoul",
    )

    assert request.workflow_name == "worker_agent"
    assert request.run_at == run_at
    assert request.timezone == "Asia/Seoul"


def test_root_is_single_tool_free_structured_output_agent() -> None:
    assert isinstance(agent_module.root_agent, Agent)
    assert agent_module.root_agent is agent_module.scheduling_agent
    assert agent_module.root_agent.sub_agents == []
    assert agent_module.root_agent.tools == []
    assert agent_module.root_agent.output_schema is agent_module.ScheduleRequest
    assert agent_module.root_agent.output_key == agent_module.SCHEDULE_REQUEST_KEY


def test_worker_agent_is_independent_tool_free_structured_output_agent() -> None:
    worker_agent = worker_agent_module.calculator_worker_agent

    assert isinstance(worker_agent, Agent)
    assert worker_agent is not agent_module.root_agent
    assert worker_agent not in agent_module.root_agent.sub_agents
    assert worker_agent.sub_agents == []
    assert worker_agent.tools == []
    assert worker_agent.output_schema is worker_agent_module.WorkerResult
    assert worker_agent.output_key == worker_agent_module.WORKER_RESULT_KEY


def test_execute_schedule_request_returns_scheduler_service_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int]] = []

    def fake_schedule_interval_task(task_name: str, seconds: int) -> str:
        calls.append((task_name, seconds))
        return "scheduler-service-confirmation"

    monkeypatch.setattr(
        agent_module, "schedule_interval_task", fake_schedule_interval_task
    )

    result = agent_module.execute_schedule_request(
        agent_module.ScheduleRequest(
            schedule_type="interval", task_name="A", seconds=5
        )
    )

    assert calls == [("A", 5)]
    assert result == "scheduler-service-confirmation"


@pytest.mark.asyncio
async def test_application_invokes_scheduler_with_extracted_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int]] = []

    def fake_schedule_interval_task(task_name: str, seconds: int) -> str:
        calls.append((task_name, seconds))
        return "Task A scheduled every 5 seconds."

    monkeypatch.setattr(
        agent_module, "schedule_interval_task", fake_schedule_interval_task
    )
    runner = StubRunner(
        request_data={
            "schedule_type": "interval",
            "task_name": "A",
            "seconds": 5,
        }
    )
    result = await agent_module.run_scheduling_request(
        "Schedule Task A every 5 seconds.",
        runner=runner,
        user_id="test_user",
        session_id="test_session",
    )

    assert calls == [("A", 5)]
    assert runner.messages == ["Schedule Task A every 5 seconds."]
    assert result == "Task A scheduled every 5 seconds."


def test_execute_date_request_returns_scheduler_service_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_at = datetime(2026, 8, 27, 3, 28)
    calls: list[tuple[datetime, str]] = []

    def fake_schedule_calculator_workflow(
        scheduled_time: datetime, timezone_name: str
    ) -> str:
        calls.append((scheduled_time, timezone_name))
        return "one-time-scheduler-confirmation"

    monkeypatch.setattr(
        agent_module,
        "schedule_calculator_workflow",
        fake_schedule_calculator_workflow,
    )
    request = agent_module.ScheduleRequest(
        schedule_type="date",
        workflow_name="calculator",
        run_at=run_at,
        timezone="Asia/Seoul",
    )

    result = agent_module.execute_schedule_request(request)

    assert calls == [(run_at, "Asia/Seoul")]
    assert result == "one-time-scheduler-confirmation"


@pytest.mark.asyncio
async def test_application_schedules_extracted_one_time_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[datetime, str]] = []

    def fake_schedule_calculator_workflow(
        scheduled_time: datetime, timezone_name: str
    ) -> str:
        calls.append((scheduled_time, timezone_name))
        return "calculator-workflow-registration-confirmed"

    monkeypatch.setattr(
        agent_module,
        "schedule_calculator_workflow",
        fake_schedule_calculator_workflow,
    )
    runner = StubRunner(
        request_data={
            "schedule_type": "date",
            "task_name": None,
            "seconds": None,
            "workflow_name": "calculator",
            "run_at": "2026-08-27T03:28:00",
            "timezone": "Asia/Seoul",
        }
    )

    result = await agent_module.run_scheduling_request(
        "Run the calculator workflow on August 27, 2026 at 3:28 AM Korea time.",
        runner=runner,
        user_id="test_user",
        session_id="date_test_session",
    )

    assert calls == [(datetime(2026, 8, 27, 3, 28), "Asia/Seoul")]
    assert result == "calculator-workflow-registration-confirmed"


@pytest.mark.asyncio
async def test_worker_agent_invocation_returns_validated_structured_result() -> None:
    runner = StubRunner(
        valid_worker_result_data(),
        output_key=worker_agent_module.WORKER_RESULT_KEY,
    )

    result = await worker_agent_module.run_worker_agent(
        runner=runner,
        user_id="worker_test_user",
        session_id="worker_test_session",
    )

    assert isinstance(result, worker_agent_module.WorkerResult)
    assert result.required_operations == [
        "add",
        "subtract",
        "multiply",
        "divide",
    ]
    assert runner.messages == [worker_agent_module.WORKER_INSTRUCTION]


@pytest.mark.asyncio
async def test_worker_agent_invocation_rejects_invalid_structured_result() -> None:
    invalid_result = valid_worker_result_data()
    invalid_result["required_operations"] = [
        "add",
        "subtract",
        "multiply",
        "multiply",
    ]
    runner = StubRunner(
        invalid_result,
        output_key=worker_agent_module.WORKER_RESULT_KEY,
    )

    with pytest.raises(worker_agent_module.WorkerResultValidationError):
        await worker_agent_module.run_worker_agent(runner=runner)


@pytest.mark.asyncio
async def test_application_schedules_extracted_worker_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[datetime, str]] = []

    def fake_schedule_worker_agent_workflow(
        scheduled_time: datetime, timezone_name: str
    ) -> str:
        calls.append((scheduled_time, timezone_name))
        return "worker-workflow-registration-confirmed"

    monkeypatch.setattr(
        agent_module,
        "schedule_worker_agent_workflow",
        fake_schedule_worker_agent_workflow,
    )
    runner = StubRunner(
        request_data={
            "schedule_type": "date",
            "task_name": None,
            "seconds": None,
            "workflow_name": "worker_agent",
            "run_at": "2026-08-27T10:10:00",
            "timezone": "Asia/Seoul",
        }
    )

    result = await agent_module.run_scheduling_request(
        "Run the worker agent workflow on August 27, 2026 at 10:10 AM Korea time.",
        runner=runner,
        user_id="test_user",
        session_id="worker_date_test_session",
    )

    assert calls == [(datetime(2026, 8, 27, 10, 10), "Asia/Seoul")]
    assert result == "worker-workflow-registration-confirmed"


def test_existing_interval_scheduler_registration_still_works() -> None:
    result = scheduler_service.schedule_interval_task("A", 10)
    job = scheduler_service.scheduler.get_job("task_A")

    assert result == "Task A scheduled every 10 seconds."
    assert job is not None
    assert job.trigger.interval.total_seconds() == 10
    assert job.max_instances == 1


def test_one_time_scheduler_preserves_seoul_date_and_timezone() -> None:
    run_at = datetime(2026, 8, 27, 3, 28)

    result = scheduler_service.schedule_calculator_workflow(
        run_at, "Asia/Seoul"
    )
    job = scheduler_service.scheduler.get_job(
        scheduler_service.CALCULATOR_WORKFLOW_JOB_ID
    )

    assert result == (
        "Calculator workflow scheduled once for "
        "2026-08-27 03:28:00 Asia/Seoul."
    )
    assert job is not None
    assert isinstance(job.trigger, DateTrigger)
    assert job.trigger.run_date == datetime(
        2026, 8, 27, 3, 28, tzinfo=ZoneInfo("Asia/Seoul")
    )
    assert getattr(job.trigger.run_date.tzinfo, "key", None) == "Asia/Seoul"
    assert job.kwargs["scheduled_time"] == job.trigger.run_date


def test_one_time_date_trigger_executes_automatically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_scheduler = BackgroundScheduler(timezone=ZoneInfo("Asia/Seoul"))
    fired = Event()
    received_times: list[datetime] = []

    def fake_workflow(scheduled_time: datetime) -> None:
        received_times.append(scheduled_time)
        fired.set()

    monkeypatch.setattr(scheduler_service, "scheduler", local_scheduler)
    monkeypatch.setattr(
        scheduler_service, "run_calculator_workflow", fake_workflow
    )
    run_at = datetime.now(ZoneInfo("Asia/Seoul")) + timedelta(milliseconds=250)

    try:
        local_scheduler.start()
        scheduler_service.schedule_calculator_workflow(run_at, "Asia/Seoul")
        assert fired.wait(timeout=2)
    finally:
        local_scheduler.shutdown(wait=True)

    assert received_times == [run_at]
    assert local_scheduler.get_jobs() == []


def test_worker_date_registration_does_not_invoke_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback_calls: list[datetime] = []

    def fake_worker_callback(scheduled_time: datetime) -> None:
        callback_calls.append(scheduled_time)

    monkeypatch.setattr(
        scheduler_service,
        "run_worker_agent_workflow",
        fake_worker_callback,
    )
    run_at = datetime(2030, 8, 27, 10, 10)

    result = scheduler_service.schedule_worker_agent_workflow(
        run_at, "Asia/Seoul"
    )
    job = scheduler_service.scheduler.get_job(
        scheduler_service.WORKER_AGENT_WORKFLOW_JOB_ID
    )

    assert result == (
        "Worker Agent workflow scheduled once for "
        "2030-08-27 10:10:00 Asia/Seoul."
    )
    assert callback_calls == []
    assert job is not None
    assert isinstance(job.trigger, DateTrigger)
    assert job.trigger.run_date == datetime(
        2030, 8, 27, 10, 10, tzinfo=ZoneInfo("Asia/Seoul")
    )
    assert job.max_instances == 1
    assert job.kwargs["scheduled_time"] == job.trigger.run_date


def test_worker_date_trigger_invokes_agent_and_writes_artifact_and_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_scheduler = BackgroundScheduler(timezone=ZoneInfo("Asia/Seoul"))
    fired = Event()
    invocation_count = 0
    workflow_results: list[str] = []
    original_workflow = scheduler_service.run_worker_agent_workflow

    async def fake_run_worker_agent() -> worker_agent_module.WorkerResult:
        nonlocal invocation_count
        invocation_count += 1
        return worker_agent_module.WorkerResult.model_validate(
            valid_worker_result_data()
        )

    def controlled_callback(scheduled_time: datetime) -> None:
        try:
            workflow_results.append(original_workflow(scheduled_time, tmp_path))
        finally:
            fired.set()

    history_path = tmp_path / "logs" / "history.log"
    history_path.parent.mkdir(parents=True)
    history_path.write_text("existing calculator history\n", encoding="utf-8")
    monkeypatch.setattr(
        scheduler_service,
        "run_worker_agent",
        fake_run_worker_agent,
    )
    monkeypatch.setattr(
        scheduler_service,
        "run_worker_agent_workflow",
        controlled_callback,
    )
    monkeypatch.setattr(scheduler_service, "scheduler", local_scheduler)
    run_at = datetime.now(ZoneInfo("Asia/Seoul")) + timedelta(milliseconds=250)

    try:
        local_scheduler.start()
        scheduler_service.schedule_worker_agent_workflow(run_at, "Asia/Seoul")
        assert invocation_count == 0
        assert fired.wait(timeout=2)
    finally:
        local_scheduler.shutdown(wait=True)

    artifact = json.loads(
        (tmp_path / "generated" / "worker_result.json").read_text(
            encoding="utf-8"
        )
    )
    history = history_path.read_text(encoding="utf-8")

    assert invocation_count == 1
    assert workflow_results == [
        "Worker Agent workflow completed with status: SUCCESS."
    ]
    assert artifact["worker_agent_name"] == "calculator_worker_agent"
    assert artifact["scheduled_time"] == run_at.isoformat()
    assert artifact["structured_result"] == valid_worker_result_data()
    assert artifact["final_status"] == "SUCCESS"
    assert artifact["actual_invocation_time"].endswith("+09:00")
    assert artifact["completed_time"].endswith("+09:00")
    assert history.startswith("existing calculator history\n")
    assert "Scheduled workflow: worker_agent" in history
    assert "Agent invocation: SUCCESS" in history
    assert "Structured output validation: SUCCESS" in history
    assert "Artifact: generated/worker_result.json" in history
    assert "Final status: SUCCESS" in history
    assert local_scheduler.get_jobs() == []


def test_worker_agent_failure_is_logged_without_artifact_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def failing_worker_agent() -> worker_agent_module.WorkerResult:
        raise RuntimeError("worker endpoint unavailable")

    monkeypatch.setattr(
        scheduler_service,
        "run_worker_agent",
        failing_worker_agent,
    )
    scheduled_time = datetime(
        2026, 8, 27, 10, 10, tzinfo=ZoneInfo("Asia/Seoul")
    )

    result = scheduler_service.run_worker_agent_workflow(
        scheduled_time, tmp_path
    )
    history = (tmp_path / "logs" / "history.log").read_text(encoding="utf-8")

    assert result == "Worker Agent workflow completed with status: FAILURE."
    assert not (tmp_path / "generated" / "worker_result.json").exists()
    assert "Scheduled workflow: worker_agent" in history
    assert "Agent invocation: FAILURE" in history
    assert "Structured output validation: NOT RUN" in history
    assert "Artifact: NOT WRITTEN" in history
    assert "RuntimeError: worker endpoint unavailable" in history
    assert "Final status: FAILURE" in history


def test_calculator_tasks_create_test_and_document_program(tmp_path: Path) -> None:
    task_a_result = scheduler_service.calculator_workflow_task_a(tmp_path)
    calculator_path = tmp_path / "generated" / "calculator.py"
    calculator = runpy.run_path(str(calculator_path))

    assert task_a_result == "generated/calculator.py created"
    assert calculator["add"](2, 3) == 5
    assert calculator["subtract"](10, 4) == 6
    assert calculator["multiply"](3, 7) == 21
    assert calculator["divide"](10, 2) == 5
    with pytest.raises(ValueError, match="division by zero"):
        calculator["divide"](1, 0)

    task_b_result = scheduler_service.calculator_workflow_task_b(tmp_path)
    task_c_result = scheduler_service.calculator_workflow_task_c(
        task_b_result, tmp_path
    )
    readme = (tmp_path / "generated" / "README.md").read_text(encoding="utf-8")

    assert task_b_result == "5/5 calculator checks passed"
    assert task_c_result == "generated/README.md created"
    assert "add(left, right)" in readme
    assert "divide(left, right)" in readme
    assert "raises `ValueError`" in readme
    assert "5/5 calculator checks passed" in readme


def test_calculator_workflow_runs_in_order_and_appends_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    execution_order: list[str] = []

    def fake_task_a(project_root: Path | None = None) -> str:
        execution_order.append("A")
        return "generated/calculator.py created"

    def fake_task_b(project_root: Path | None = None) -> str:
        execution_order.append("B")
        return "5/5 calculator checks passed"

    def fake_task_c(
        verification_result: str, project_root: Path | None = None
    ) -> str:
        execution_order.append("C")
        assert verification_result == "5/5 calculator checks passed"
        return "generated/README.md created"

    monkeypatch.setattr(scheduler_service, "calculator_workflow_task_a", fake_task_a)
    monkeypatch.setattr(scheduler_service, "calculator_workflow_task_b", fake_task_b)
    monkeypatch.setattr(scheduler_service, "calculator_workflow_task_c", fake_task_c)
    scheduled_time = datetime(2026, 8, 27, 3, 28, tzinfo=ZoneInfo("Asia/Seoul"))

    first_result = scheduler_service.run_calculator_workflow(
        scheduled_time, tmp_path
    )
    second_result = scheduler_service.run_calculator_workflow(
        scheduled_time, tmp_path
    )
    history = (tmp_path / "logs" / "history.log").read_text(encoding="utf-8")

    assert first_result == "Calculator workflow completed with status: SUCCESS."
    assert second_result == "Calculator workflow completed with status: SUCCESS."
    assert execution_order == ["A", "B", "C", "A", "B", "C"]
    assert history.count("Scheduled workflow: calculator") == 2
    assert history.count("Final status: SUCCESS") == 2
    assert "Scheduled time: 2026-08-27 03:28:00 Asia/Seoul" in history


def test_calculator_workflow_failure_is_logged_and_stops_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    execution_order: list[str] = []

    def fake_task_a(project_root: Path | None = None) -> str:
        execution_order.append("A")
        return "generated/calculator.py created"

    def failing_task_b(project_root: Path | None = None) -> str:
        execution_order.append("B")
        raise RuntimeError("calculator verification failed")

    def forbidden_task_c(
        verification_result: str, project_root: Path | None = None
    ) -> str:
        execution_order.append("C")
        return "unexpected"

    monkeypatch.setattr(scheduler_service, "calculator_workflow_task_a", fake_task_a)
    monkeypatch.setattr(
        scheduler_service, "calculator_workflow_task_b", failing_task_b
    )
    monkeypatch.setattr(
        scheduler_service, "calculator_workflow_task_c", forbidden_task_c
    )
    scheduled_time = datetime(2026, 8, 27, 3, 28, tzinfo=ZoneInfo("Asia/Seoul"))

    result = scheduler_service.run_calculator_workflow(scheduled_time, tmp_path)
    history = (tmp_path / "logs" / "history.log").read_text(encoding="utf-8")

    assert result == "Calculator workflow completed with status: FAILURE."
    assert execution_order == ["A", "B"]
    assert "Task A: SUCCESS - generated/calculator.py created" in history
    assert (
        "Task B: FAILURE - RuntimeError: calculator verification failed" in history
    )
    assert "Task C: NOT RUN - dependency did not complete" in history
    assert "Final status: FAILURE" in history

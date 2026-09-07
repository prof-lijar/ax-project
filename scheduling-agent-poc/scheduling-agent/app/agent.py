# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime as datetime_module
import os
from datetime import datetime
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.scheduler_service import (
    schedule_calculator_workflow,
    schedule_interval_task,
    schedule_worker_agent_workflow,
)

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner, Runner
from google.genai import types
from pydantic import BaseModel, Field, ValidationError, model_validator

MODEL = "openai/gemma-4-31b"
SCHEDULE_REQUEST_KEY = "schedule_request"


class ScheduleRequest(BaseModel):
    schedule_type: Literal["interval", "date"]
    task_name: Literal["A", "B", "C"] | None = None
    seconds: int | None = Field(default=None, gt=0)
    workflow_name: Literal["calculator", "worker_agent"] | None = None
    run_at: datetime | None = None
    timezone: Literal["Asia/Seoul"] | None = None

    @model_validator(mode="after")
    def validate_schedule_fields(self) -> "ScheduleRequest":
        if self.schedule_type == "interval":
            if self.task_name is None or self.seconds is None:
                raise ValueError("interval schedules require task_name and seconds")
            if any(
                value is not None
                for value in (self.workflow_name, self.run_at, self.timezone)
            ):
                raise ValueError("interval schedules cannot include date fields")
        else:
            if (
                self.workflow_name not in {"calculator", "worker_agent"}
                or self.run_at is None
                or self.timezone != "Asia/Seoul"
            ):
                raise ValueError(
                    "date schedules require a supported workflow, run_at, and "
                    "Asia/Seoul timezone"
                )
            if self.task_name is not None or self.seconds is not None:
                raise ValueError("date schedules cannot include interval fields")

            # `run_at` is a local wall-clock value; `timezone` supplies its zone.
            # Some OpenAI-compatible structured-output models add a UTC marker
            # even when asked for local time, so discard that marker rather than
            # silently shifting the requested clock time during scheduling.
            self.run_at = self.run_at.replace(tzinfo=None)

        return self


def execute_schedule_request(request: ScheduleRequest) -> str:
    if request.schedule_type == "interval":
        assert request.task_name is not None
        assert request.seconds is not None
        return schedule_interval_task(request.task_name, request.seconds)

    assert request.run_at is not None
    assert request.timezone is not None
    if request.workflow_name == "calculator":
        return schedule_calculator_workflow(request.run_at, request.timezone)

    assert request.workflow_name == "worker_agent"
    return schedule_worker_agent_workflow(request.run_at, request.timezone)


def schedule_extracted_request(extracted_request: object) -> str:
    """Validate extracted data and return the scheduling service result."""

    try:
        request = ScheduleRequest.model_validate(extracted_request)
    except ValidationError:
        return "Unable to schedule task: no valid scheduling request was produced."

    return execute_schedule_request(request)


async def run_scheduling_request(
    message: str,
    *,
    runner: Runner | None = None,
    user_id: str = "scheduling_user",
    session_id: str | None = None,
) -> str:
    """Run structured extraction, then schedule deterministically in Python."""

    owns_runner = runner is None
    if runner is None:
        runner = InMemoryRunner(agent=root_agent, app_name=app.name)

    session = await runner.session_service.create_session(
        app_name=app.name,
        user_id=user_id,
        session_id=session_id or str(uuid4()),
    )
    extracted_request = None

    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=types.Content(
                role="user",
                parts=[types.Part.from_text(text=message)],
            ),
        ):
            state_delta = event.actions.state_delta if event.actions else {}
            if SCHEDULE_REQUEST_KEY in state_delta:
                extracted_request = state_delta[SCHEDULE_REQUEST_KEY]
    finally:
        if owns_runner:
            await runner.close()

    return schedule_extracted_request(extracted_request)


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        city: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime_module.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"

scheduling_agent = Agent(
    name="scheduling_agent",
    model=LiteLlm(
        model=MODEL,
        api_base=os.environ["OPENAI_API_BASE"],
        api_key=os.environ["OPENAI_API_KEY"],
    ),
    instruction="""
Extract one validated scheduling request from the user's message.

Return only the requested structured output.

Supported interval tasks:
- Task A
- Task B
- Task C

Supported one-time workflow:
- calculator
- worker_agent

For a recurring interval request, return:
- schedule_type: interval
- task_name: A, B, or C
- seconds: a positive integer interval in seconds
- workflow_name, run_at, and timezone: null

For the calculator workflow at an exact date and time, return:
- schedule_type: date
- workflow_name: calculator
- run_at: the exact local wall-clock date and time in ISO 8601 format, without
  a Z suffix or UTC offset
- timezone: Asia/Seoul
- task_name and seconds: null

For the Worker Agent workflow at an exact date and time, return:
- schedule_type: date
- workflow_name: worker_agent
- run_at: the exact local wall-clock date and time in ISO 8601 format, without
  a Z suffix or UTC offset
- timezone: Asia/Seoul
- task_name and seconds: null

Do not infer cron schedules or other workflows.

Do not schedule anything and do not claim that scheduling succeeded.
""",
    output_schema=ScheduleRequest,
    output_key=SCHEDULE_REQUEST_KEY,
    tools=[],
)

root_agent = scheduling_agent

app = App(
    root_agent=root_agent,
    name="app",
)

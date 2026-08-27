"""Independent ADK Worker Agent invoked only by a scheduled callback."""

import os
from typing import Literal
from uuid import uuid4

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner, Runner
from google.genai import types
from pydantic import BaseModel, Field, ValidationError, field_validator

MODEL = "openai/gemma-4-31b"
WORKER_AGENT_NAME = "calculator_worker_agent"
WORKER_APP_NAME = "calculator_worker_app"
WORKER_RESULT_KEY = "worker_result"
WORKER_INSTRUCTION = (
    "Create a simple Python calculator implementation plan and describe the "
    "tests that should verify add, subtract, multiply, divide, and "
    "division-by-zero behavior."
)


class WorkerResult(BaseModel):
    implementation_description: str = Field(min_length=1)
    required_operations: list[
        Literal["add", "subtract", "multiply", "divide"]
    ] = Field(min_length=4, max_length=4)
    test_plan: list[str] = Field(min_length=5)
    readme_summary: str = Field(min_length=1)

    @field_validator("required_operations")
    @classmethod
    def require_all_operations(cls, operations: list[str]) -> list[str]:
        expected = {"add", "subtract", "multiply", "divide"}
        if len(set(operations)) != 4 or set(operations) != expected:
            raise ValueError("required_operations must contain each operation once")
        return operations


class WorkerResultValidationError(ValueError):
    """Raised when an Agent run does not produce a valid WorkerResult."""


calculator_worker_agent = Agent(
    name=WORKER_AGENT_NAME,
    model=LiteLlm(
        model=MODEL,
        api_base=os.environ["OPENAI_API_BASE"],
        api_key=os.environ["OPENAI_API_KEY"],
    ),
    instruction="""
Produce a structured implementation plan for a small Python calculator.

The calculator must support exactly these required operations, each listed
once: add, subtract, multiply, and divide.

The test plan must contain at least five concise checks covering each required
operation and division by zero raising ValueError.

The README summary must describe the planned calculator, its operations, basic
usage, and division-by-zero behavior.

Do not execute code, call tools, access the filesystem, or claim that any file
was created. Return only the requested structured output.
""",
    output_schema=WorkerResult,
    output_key=WORKER_RESULT_KEY,
    tools=[],
)


async def run_worker_agent(
    instruction: str = WORKER_INSTRUCTION,
    *,
    runner: Runner | None = None,
    user_id: str = "worker_user",
    session_id: str | None = None,
) -> WorkerResult:
    """Invoke the independent Worker Agent and validate its structured output."""

    owns_runner = runner is None
    if runner is None:
        runner = InMemoryRunner(
            agent=calculator_worker_agent,
            app_name=WORKER_APP_NAME,
        )

    session = await runner.session_service.create_session(
        app_name=WORKER_APP_NAME,
        user_id=user_id,
        session_id=session_id or str(uuid4()),
    )
    extracted_result = None

    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=types.Content(
                role="user",
                parts=[types.Part.from_text(text=instruction)],
            ),
        ):
            state_delta = event.actions.state_delta if event.actions else {}
            if WORKER_RESULT_KEY in state_delta:
                extracted_result = state_delta[WORKER_RESULT_KEY]
    finally:
        if owns_runner:
            await runner.close()

    try:
        return WorkerResult.model_validate(extracted_result)
    except ValidationError as error:
        raise WorkerResultValidationError(
            "Worker Agent did not produce a valid structured result"
        ) from error

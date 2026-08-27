from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from google.adk.agents import Agent
from google.adk.agents.run_config import RunConfig
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agent import create_scout_agent
from app.config import ScoutSettings
from app.models import ScoutRunRequest, ScoutRunResponse
from app.services.persistence import ArtifactStore
from app.tools.scout import ScoutWebToolset
from app.tools.web import DdgsSearchProvider, FetchLimits, WebFetcher


@dataclass(frozen=True, slots=True)
class AgentExecution:
    report: str
    tool_calls: tuple[str, ...]


class ResearchAgentExecutor(Protocol):
    async def execute(
        self,
        request: ScoutRunRequest,
        run_id: str,
        toolset: ScoutWebToolset,
    ) -> AgentExecution: ...


AgentRunner = Callable[[Agent, str, str, str, int], Awaitable[AgentExecution]]
ToolsetFactory = Callable[[str], ScoutWebToolset]


async def run_agent_once(
    agent: Agent,
    prompt: str,
    app_name: str,
    session_id: str,
    max_llm_calls: int,
) -> AgentExecution:
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=app_name,
        user_id="scout-api",
        session_id=session_id,
    )
    runner = Runner(
        app_name=app_name,
        agent=agent,
        session_service=session_service,
    )
    final_text = ""
    tool_calls: list[str] = []
    async for event in runner.run_async(
        user_id="scout-api",
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
        run_config=RunConfig(max_llm_calls=max_llm_calls),
    ):
        tool_calls.extend(call.name for call in event.get_function_calls() if call.name is not None)
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(
                part.text or "" for part in event.content.parts if part.text is not None
            ).strip()
    if not final_text:
        raise RuntimeError(f"ADK agent {agent.name} produced no final response")
    return AgentExecution(report=final_text, tool_calls=tuple(tool_calls))


class AdkResearchAgentExecutor:
    """Runs the single ADK Agent and lets its native function-call loop research."""

    def __init__(
        self,
        settings: ScoutSettings,
        *,
        agent_runner: AgentRunner = run_agent_once,
    ) -> None:
        self._settings = settings
        self._agent_runner = agent_runner

    async def execute(
        self,
        request: ScoutRunRequest,
        run_id: str,
        toolset: ScoutWebToolset,
    ) -> AgentExecution:
        prompt = (
            "Research this request using your registered web tools, then return the required "
            "Markdown report. Request JSON:\n"
            + json.dumps(request.model_dump(), ensure_ascii=False)
        )
        return await self._agent_runner(
            create_scout_agent(self._settings, toolset),
            prompt,
            "ansimk_scout_agent",
            run_id,
            self._settings.max_agent_llm_calls,
        )


class ScoutRunService:
    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        agent_executor: ResearchAgentExecutor,
        toolset_factory: ToolsetFactory,
        settings: ScoutSettings | None = None,
    ) -> None:
        self._artifact_store = artifact_store
        self._agent_executor = agent_executor
        self._toolset_factory = toolset_factory
        self._settings = settings

    def is_ready(self) -> bool:
        return self._settings is None or self._settings.is_model_ready

    async def run(self, request: ScoutRunRequest) -> ScoutRunResponse:
        run_id = self._artifact_store.create_run()
        run_started = time.monotonic()
        phase = "agent setup"
        toolset: ScoutWebToolset | None = None
        try:
            toolset = self._toolset_factory(run_id)
            phase = "agent"
            agent_started = time.monotonic()
            self._artifact_store.append_event(
                run_id,
                "agent_started",
                agent_name="ansimk_scout_agent",
                registered_tools=["web_search", "web_fetch_and_extract"],
                search_call_limit=toolset.max_search_calls,
                search_result_limit=toolset.search_result_limit,
                fetch_call_limit=toolset.max_fetch_calls,
            )
            execution = await self._agent_executor.execute(request, run_id, toolset)
            fetched_urls = toolset.successful_fetched_urls
            self._artifact_store.append_event(
                run_id,
                "agent_completed",
                tool_call_count=len(execution.tool_calls),
                tool_names=list(execution.tool_calls),
                search_call_count=toolset.search_call_count,
                fetch_call_count=toolset.fetch_call_count,
                successful_fetch_count=len(fetched_urls),
                report_character_count=len(execution.report),
                duration_ms=_duration_ms(agent_started),
            )

            phase = "report validation"
            artifact = self._artifact_store.save_report(
                run_id,
                execution.report,
                fetched_urls=fetched_urls,
            )
            self._artifact_store.append_event(
                run_id,
                "run_succeeded",
                duration_ms=_duration_ms(run_started),
                successful_fetch_count=len(fetched_urls),
            )
            return ScoutRunResponse(
                run_id=run_id,
                status="success",
                report=execution.report,
                sources=artifact.sources,
                report_artifact=artifact.report_artifact,
                log_artifact=artifact.log_artifact,
            )
        except Exception as exc:
            self._artifact_store.append_event(
                run_id,
                "run_failed",
                error=f"Scout run failed during {phase}.",
                error_code=type(exc).__name__,
                duration_ms=_duration_ms(run_started),
            )
            raise
        finally:
            if toolset is not None:
                try:
                    await toolset.aclose()
                except Exception:
                    pass


def _duration_ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


def build_default_run_service(settings: ScoutSettings) -> ScoutRunService:
    limits = FetchLimits(
        timeout_seconds=settings.request_timeout_seconds,
        max_redirects=settings.max_redirects,
        max_response_bytes=settings.max_response_bytes,
        max_extracted_characters=settings.max_extracted_characters,
    )

    def create_toolset(run_id: str) -> ScoutWebToolset:
        return ScoutWebToolset(
            run_id=run_id,
            event_logger=artifact_store,
            search_provider=DdgsSearchProvider(),
            fetcher=WebFetcher(limits=limits),
            max_search_calls=settings.search_call_limit,
            search_result_limit=settings.search_result_limit,
            max_fetch_calls=settings.fetch_page_limit,
        )

    artifact_store = ArtifactStore(settings.output_root)
    return ScoutRunService(
        artifact_store=artifact_store,
        agent_executor=AdkResearchAgentExecutor(settings),
        toolset_factory=create_toolset,
        settings=settings,
    )

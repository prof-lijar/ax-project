from __future__ import annotations

from collections.abc import AsyncGenerator

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import FunctionTool
from google.genai import types
from pydantic import Field

from app.agent import SCOUT_INSTRUCTION, app, create_scout_agent
from app.config import ScoutSettings
from app.models import FetchedPage, SearchResult
from app.services.run_service import run_agent_once
from app.tools.scout import NullEventLogger, ScoutWebToolset


class StaticProvider:
    async def search(self, query: str, limit: int) -> list[SearchResult]:
        del query, limit
        return [SearchResult(title="Evidence", url="https://example.com/evidence")]


class StaticFetcher:
    async def fetch(self, url: str) -> FetchedPage:
        return FetchedPage(
            url=url,
            title="Evidence",
            text="Bounded evidence text.",
            content_type="text/html",
            truncated=False,
        )

    async def aclose(self) -> None:
        return None


class ScriptedToolCallingModel(BaseLlm):
    turn: int = 0
    observed_function_responses: list[str] = Field(default_factory=list)

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse]:
        del stream
        self.observed_function_responses.extend(
            part.function_response.name
            for content in llm_request.contents
            for part in content.parts or []
            if part.function_response is not None and part.function_response.name is not None
        )
        self.turn += 1
        if self.turn == 1:
            parts = [
                types.Part.from_function_call(
                    name="web_search",
                    args={"query": "example evidence"},
                )
            ]
        elif self.turn == 2:
            parts = [
                types.Part.from_function_call(
                    name="web_fetch_and_extract",
                    args={"url": "https://example.com/evidence"},
                )
            ]
        else:
            parts = [
                types.Part(
                    text="""# Scout Report

## Topic

Example research

## Summary

The fetched evidence was summarized.

## Key Findings

- The controlled ADK loop used both registered function tools.

## Sources

- https://example.com/evidence
"""
                )
            ]
        yield LlmResponse(content=types.Content(role="model", parts=parts))


def settings(tmp_path) -> ScoutSettings:
    return ScoutSettings(
        api_base="http://model.internal/v1",
        api_key="test-key",
        model="internal-model",
        output_root=tmp_path,
    )


def toolset() -> ScoutWebToolset:
    return ScoutWebToolset(
        run_id="test-run",
        event_logger=NullEventLogger(),
        search_provider=StaticProvider(),
        fetcher=StaticFetcher(),
        max_search_calls=3,
        search_result_limit=6,
        max_fetch_calls=3,
    )


def test_single_adk_agent_registers_only_bounded_web_function_tools(tmp_path) -> None:
    agent = create_scout_agent(settings(tmp_path), toolset())

    assert agent.name == "ansimk_scout_agent"
    assert agent.output_schema is None
    assert agent.sub_agents == []
    assert all(isinstance(tool, FunctionTool) for tool in agent.tools)
    assert [tool.name for tool in agent.tools] == ["web_search", "web_fetch_and_extract"]
    assert agent.instruction == SCOUT_INSTRUCTION
    assert "untrusted evidence" in agent.instruction
    assert "filesystem" in agent.instruction
    assert app.name == "app"
    assert app.root_agent.name == "ansimk_scout_agent"
    assert [tool.name for tool in app.root_agent.tools] == [
        "web_search",
        "web_fetch_and_extract",
    ]


def test_agent_uses_isolated_litellm_configuration(tmp_path) -> None:
    agent = create_scout_agent(settings(tmp_path), toolset())

    assert agent.model.model == "openai/internal-model"
    assert agent.model._additional_args == {
        "api_base": "http://model.internal/v1",
        "api_key": "test-key",
    }


async def test_controlled_adk_native_tool_call_loop_runs_end_to_end(tmp_path) -> None:
    model = ScriptedToolCallingModel(model="scripted-tool-model")
    bounded_tools = toolset()
    agent = create_scout_agent(settings(tmp_path), bounded_tools, model=model)

    execution = await run_agent_once(agent, "Research example evidence", "app", "session-1", 8)

    assert execution.tool_calls == ("web_search", "web_fetch_and_extract")
    assert model.observed_function_responses == [
        "web_search",
        "web_search",
        "web_fetch_and_extract",
    ]
    assert bounded_tools.successful_fetched_urls == {"https://example.com/evidence"}
    assert execution.report.startswith("# Scout Report")

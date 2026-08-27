from __future__ import annotations

from app.agent import app, create_planning_agent, create_summary_agent
from app.config import ScoutSettings
from app.models import SearchPlan


def test_both_adk_stages_are_tool_free(tmp_path) -> None:
    settings = ScoutSettings(
        api_base="http://model.internal/v1",
        api_key="test-key",
        model="internal-model",
        output_root=tmp_path,
    )

    planning_agent = create_planning_agent(settings)
    summary_agent = create_summary_agent(settings)

    assert planning_agent.name == "search_planning_agent"
    assert planning_agent.output_schema is SearchPlan
    assert planning_agent.tools == []
    assert planning_agent.sub_agents == []
    assert summary_agent.name == "ansimk_scout_agent"
    assert summary_agent.output_schema is None
    assert summary_agent.tools == []
    assert summary_agent.sub_agents == []
    assert "untrusted data" in summary_agent.instruction
    assert "filesystem" in summary_agent.instruction
    assert app.name == "app"
    assert app.root_agent.name == "ansimk_scout_agent"


def test_both_stages_use_isolated_litellm_configuration(tmp_path) -> None:
    settings = ScoutSettings(
        api_base="http://model.internal/v1",
        api_key="test-key",
        model="internal-model",
        output_root=tmp_path,
    )

    for agent in (create_planning_agent(settings), create_summary_agent(settings)):
        assert agent.model.model == "openai/internal-model"
        assert agent.model._additional_args == {
            "api_base": "http://model.internal/v1",
            "api_key": "test-key",
        }

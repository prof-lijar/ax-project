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

from app.agent import create_agent, get_current_time, get_weather
from app.config import Settings


def test_weather_tool_supports_new_york() -> None:
    result = get_weather("New York")

    assert result["status"] == "success"
    assert "25 degrees Celsius" in result["report"]


def test_weather_tool_rejects_an_unknown_city() -> None:
    assert get_weather("Seoul") == {
        "status": "error",
        "error_message": "Weather information for 'Seoul' is not available.",
    }


def test_time_tool_supports_new_york() -> None:
    result = get_current_time("New York")

    assert result["status"] == "success"
    assert result["report"].startswith("The current time in New York is ")


def test_agent_uses_litellm_and_registers_both_tools() -> None:
    agent = create_agent(
        Settings(
            api_base="http://model.internal/v1",
            api_key="test-key",
            model="gemma-4-31b",
        )
    )

    assert agent.name == "weather_time_agent"
    assert agent.model.model == "openai/gemma-4-31b"
    assert agent.model._additional_args == {
        "api_base": "http://model.internal/v1",
        "api_key": "test-key",
    }
    assert [tool.__name__ for tool in agent.tools] == [
        "get_weather",
        "get_current_time",
        "web_search",
    ]

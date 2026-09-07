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

from app import tools


class StubDDGS:
    def __init__(self, timeout: int) -> None:
        assert timeout == 10

    def text(
        self,
        query: str,
        *,
        region: str,
        safesearch: str,
        max_results: int,
    ) -> list[dict[str, str]]:
        assert query == "Python documentation"
        assert region == "us-en"
        assert safesearch == "moderate"
        assert max_results == tools.MAX_SEARCH_RESULTS
        return [
            {
                "title": "Python documentation",
                "href": "https://docs.python.org/3/",
                "body": "The official Python documentation.",
            }
        ]


def test_web_search_returns_normalized_results(monkeypatch) -> None:
    monkeypatch.setattr(tools, "DDGS", StubDDGS)

    result = tools.web_search("  Python documentation  ")

    assert result == {
        "status": "success",
        "query": "Python documentation",
        "results": [
            {
                "title": "Python documentation",
                "url": "https://docs.python.org/3/",
                "snippet": "The official Python documentation.",
            }
        ],
    }


def test_web_search_rejects_an_empty_query() -> None:
    assert tools.web_search("  ") == {
        "status": "error",
        "error_message": "The web search query must not be empty.",
    }

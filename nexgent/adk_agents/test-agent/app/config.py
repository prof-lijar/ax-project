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

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=False)

DEFAULT_API_BASE = "http://192.168.0.17:8000/v1"
DEFAULT_MODEL = "gemma-4-31b"


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings for the local OpenAI-compatible model endpoint."""

    api_base: str = DEFAULT_API_BASE
    api_key: str | None = None
    model: str = DEFAULT_MODEL

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            api_base=os.getenv("OPENAI_API_BASE", DEFAULT_API_BASE).strip(),
            api_key=_clean_env("OPENAI_API_KEY"),
            model=os.getenv("TEST_AGENT_MODEL", DEFAULT_MODEL).strip(),
        )

    @property
    def litellm_model(self) -> str:
        return self.model if "/" in self.model else f"openai/{self.model}"


def _clean_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None

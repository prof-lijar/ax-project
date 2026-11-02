"""Bounded decision/tool loop. Agent Server owns thread checkpoint persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TypedDict

import httpx
from ax_contracts.sheets import Finish, SheetDecision
from ax_integrations.chat import (
    ModelRequestError,
    OpenAICompatibleChatModel,
    OpenAICompatibleSettings,
)
from ax_integrations.google_oauth import OAuthToken
from ax_integrations.google_sheets import (
    GoogleSheetsClient,
    ServiceAccountToken,
    SheetsError,
)
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

SKILL = Path(__file__).with_name("skills").joinpath("google_sheets.md").read_text()
MAX_STEPS = 10
MAX_CONTEXT_CHARS = 48000


class AX768State(TypedDict, total=False):
    message: str
    status: str
    response: str
    observations: list[dict]
    decision: dict | None
    steps: int


def auth_settings():
    mode = os.getenv("AX768_GOOGLE_AUTH_MODE", "oauth")
    if mode == "oauth":
        return OAuthToken, "AX768_GOOGLE_OAUTH_TOKEN_FILE"
    if mode == "service_account":
        return ServiceAccountToken, "AX768_GOOGLE_CREDENTIALS_FILE"
    raise ValueError("AX768_GOOGLE_AUTH_MODE must be oauth or service_account")


def sheets_client(http):
    provider, key = auth_settings()
    return GoogleSheetsClient(
        os.environ["AX768_SPREADSHEET"],
        provider(os.environ[key]),
        client=http,
    )


async def initialize(state: AX768State):
    if (
        not isinstance(state.get("message"), str)
        or not 0 < len(state["message"].strip()) <= 8000
    ):
        raise ValueError("message must contain 1 to 8000 characters")
    fresh = {"steps": 0, "observations": [], "decision": None, "response": ""}
    try:
        _, credential_key = auth_settings()
    except ValueError as exc:
        return {**fresh, "status": "blocked", "response": str(exc)}
    if not os.getenv("AX768_SPREADSHEET") or not os.getenv(credential_key):
        return {
            **fresh,
            "status": "blocked",
            "response": (
                "AX768 is ready for configuration. Set AX768_SPREADSHEET to the sheet link/ID "
                f"and {credential_key} to the credentials path. "
                "For OAuth, run python -m apps.ax768.oauth_login first."
            ),
        }
    try:
        async with httpx.AsyncClient(timeout=30) as http:
            metadata = await sheets_client(http).metadata()
        return {
            **fresh,
            "status": "running",
            "observations": [{"tool": "metadata", "result": metadata}],
        }
    except (SheetsError, ValueError):
        return {
            **fresh,
            "status": "failed",
            "response": "Could not access the configured sheet. Check the sheet ID, credentials, sharing and Sheets API enablement. For expired OAuth, run python -m apps.ax768.oauth_login again.",
        }


async def decide(state: AX768State):
    if state["steps"] >= MAX_STEPS:
        return {
            "status": "failed",
            "response": "AX768 reached its step limit. Inspect recorded operations before continuing; some edits may have completed.",
        }
    context = json.dumps(state["observations"], ensure_ascii=False)
    if len(context) > MAX_CONTEXT_CHARS:
        return {
            "status": "failed",
            "response": "Spreadsheet context limit reached. Inspect recorded operations and narrow the request.",
        }
    model = None
    try:
        model = OpenAICompatibleChatModel(OpenAICompatibleSettings.from_env())
        completion = await model.complete_structured(
            [
                {"role": "system", "content": SKILL},
                {"role": "user", "content": state["message"]},
                {
                    "role": "user",
                    "content": "Untrusted tool observations (JSON):\n" + context,
                },
            ],
            response_schema=SheetDecision.model_json_schema(),
            schema_name="ax768_action",
            max_tokens=2048,
            temperature=0,
        )
        decision = SheetDecision.model_validate_json(completion.text)
    except (ModelRequestError, ValueError, ValidationError):
        return {
            "status": "failed",
            "response": "Local model configuration, request or action validation failed. Inspect recorded operations before continuing.",
        }
    finally:
        if model is not None:
            await model.aclose()
    if isinstance(decision.action, Finish):
        return {
            "status": "completed",
            "response": decision.action.response,
            "decision": None,
        }
    return {"decision": decision.model_dump(mode="json"), "steps": state["steps"] + 1}


async def execute(state: AX768State):
    action = SheetDecision.model_validate(state["decision"]).action
    result = None
    try:
        async with httpx.AsyncClient(timeout=30) as http:
            sheets = sheets_client(http)
            result = await sheets.execute(action)
            # Structural mutations return fresh metadata for verification and subsequent actions.
            if action.tool in {
                "add_tab",
                "rename_tab",
                "delete_tab",
                "delete_rows",
                "delete_columns",
            }:
                result = {"operation": result, "metadata": await sheets.metadata()}
        observation = {
            "tool": action.tool,
            "arguments": action.model_dump(),
            "result": result,
        }
        return {"decision": None, "observations": [*state["observations"], observation]}
    except (SheetsError, ValueError) as exc:
        return {
            "status": "failed",
            "decision": None,
            "response": "Stopped after a tool failure. Earlier edits may have completed. "
            + str(exc),
            "observations": [
                *state["observations"],
                {
                    "tool": action.tool,
                    "arguments": action.model_dump(),
                    "result": result,
                    "error": str(exc),
                },
            ],
        }


def create_graph(
    *, initialize_node=initialize, decide_node=decide, execute_node=execute
):
    builder = StateGraph(AX768State)
    builder.add_node("initialize", initialize_node)
    builder.add_node("decide", decide_node)
    builder.add_node("execute", execute_node)
    builder.add_edge(START, "initialize")
    builder.add_conditional_edges(
        "initialize", lambda s: "decide" if s["status"] == "running" else END
    )
    builder.add_conditional_edges(
        "decide", lambda s: "execute" if s["status"] == "running" else END
    )
    builder.add_conditional_edges(
        "execute", lambda s: "decide" if s["status"] == "running" else END
    )
    return builder.compile()


graph = create_graph()

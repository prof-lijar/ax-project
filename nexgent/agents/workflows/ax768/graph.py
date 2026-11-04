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

from workflows.ax768.address_search import result_message as address_result_message
from workflows.ax768.cases import case_action
from workflows.ax768.city_search import result_message as city_result_message
from workflows.ax768.city_search import search_user_sheets
from workflows.ax768.signal_check import requested_name, result_message

SKILL = Path(__file__).with_name("skills").joinpath("google_sheets.md").read_text()
MAX_STEPS = 10
MAX_CONTEXT_CHARS = 48000


class AX768State(TypedDict, total=False):
    message: str
    case_id: str | None
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
        search_sheet_id=int(os.environ["AX768_NAME_SEARCH_SHEET_ID"])
        if os.getenv("AX768_NAME_SEARCH_SHEET_ID")
        else None,
    )


def address_sheets_client(http):
    provider, key = auth_settings()
    return GoogleSheetsClient(
        os.environ["AX768_CASE_2_2_SPREADSHEET"],
        provider(os.environ[key]),
        client=http,
        search_sheet_id=int(os.environ["AX768_CASE_2_2_SHEET_ID"]),
        address_columns=os.getenv("AX768_CASE_2_2_ADDRESS_COLUMNS") or None,
    )


def person_sheets_client(http):
    provider, key = auth_settings()
    return GoogleSheetsClient(
        os.environ["AX768_CASE_2_3_SPREADSHEET"],
        provider(os.environ[key]),
        client=http,
        search_sheet_id=int(os.environ["AX768_CASE_2_3_SHEET_ID"]),
        person_name_column=os.environ["AX768_CASE_2_3_NAME_COLUMN"],
        person_address_column=os.environ["AX768_CASE_2_3_ADDRESS_COLUMN"],
        search_start_row=int(os.environ["AX768_CASE_2_3_START_ROW"]),
    )


def client_for_case(http, case_id):
    if case_id in {"2.3", "4.3", "6.3"}:
        return person_sheets_client(http)
    return address_sheets_client(http) if case_id == "2.2" else sheets_client(http)


async def initialize(state: AX768State):
    if (
        not isinstance(state.get("message"), str)
        or not 0 < len(state["message"].strip()) <= 8000
    ):
        raise ValueError("message must contain 1 to 8000 characters")
    fresh = {"steps": 0, "observations": [], "decision": None, "response": ""}
    try:
        case_action(state.get("case_id"), state["message"])
    except ValueError as exc:
        return {**fresh, "status": "blocked", "response": str(exc)}
    try:
        _, credential_key = auth_settings()
    except ValueError as exc:
        return {**fresh, "status": "blocked", "response": str(exc)}
    target_keys = (
        ("AX768_CASE_2_2_SPREADSHEET", "AX768_CASE_2_2_SHEET_ID")
        if state.get("case_id") == "2.2"
        else ("AX768_SPREADSHEET",)
    )
    if state.get("case_id") in {"2.3", "4.3", "6.3"}:
        target_keys = tuple(
            "AX768_CASE_2_3_" + key
            for key in (
                "SPREADSHEET",
                "SHEET_ID",
                "NAME_COLUMN",
                "ADDRESS_COLUMN",
                "START_ROW",
            )
        )
    if state.get("case_id") in {"4.2", "6.2"}:
        target_keys = ()  # Fixed approved roster targets are owned by city_search.
    if any(not os.getenv(key) for key in (*target_keys, credential_key)):
        return {
            **fresh,
            "status": "blocked",
            "response": (
                f"AX768 is ready for configuration. Set {' and '.join(target_keys)} "
                f"and {credential_key} to the credentials path. "
                "For OAuth, run python -m apps.ax768.oauth_login first."
            ),
        }
    try:
        if state.get("case_id") in {"4.2", "6.2"}:
            return {**fresh, "status": "running"}
        async with httpx.AsyncClient(timeout=30) as http:
            metadata = await client_for_case(http, state.get("case_id")).metadata()
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
    try:
        selected = case_action(state.get("case_id"), state.get("message", ""))
    except ValueError as exc:
        return {"status": "blocked", "decision": None, "response": str(exc)}
    if selected is not None:
        return {
            "decision": {"schema_version": "1", "action": selected.model_dump()},
            "steps": state.get("steps", 0) + 1,
        }
    # This documented shorthand grants exactly one name-highlight action.
    name = requested_name(state.get("message", ""))
    if name:
        return {
            "decision": {
                "schema_version": "1",
                "action": {
                    "tool": "find_and_highlight_name",
                    "name": name,
                },
            },
            "steps": state.get("steps", 0) + 1,
        }
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
        if state.get("case_id") in {"4.2", "6.2"}:
            if action.tool != "search_user_sheets":
                raise ValueError(
                    "Cases 4.2/6.2 permit only read-only user-sheet lookup"
                )
            provider, key = auth_settings()
            async with httpx.AsyncClient(timeout=30) as http:
                result = await search_user_sheets(
                    http, provider(os.environ[key]), action
                )
            return {
                "decision": None,
                "status": "failed" if result["status"] == "failed" else "completed",
                "response": city_result_message(result),
                "observations": [
                    *state["observations"],
                    {
                        "tool": action.tool,
                        "arguments": action.model_dump(),
                        "result": result,
                    },
                ],
            }
        if action.tool == "search_user_sheets":
            raise ValueError("Select --case 4.2 or --case 6.2 for user-sheet lookup")
        address_tools = {"search_address", "find_and_highlight_address_row"}
        person_tool = "find_and_highlight_person_row"
        if state.get("case_id") in {"2.3", "4.3", "6.3"} and action.tool != person_tool:
            raise ValueError(
                "Cases 2.3/4.3/6.3 permit only same-row name/address search and highlighting"
            )
        if action.tool == person_tool and state.get("case_id") not in {
            "2.3",
            "4.3",
            "6.3",
        }:
            raise ValueError(
                "Select --case 2.3, --case 4.3 or --case 6.3 for AS name/address search"
            )
        if state.get("case_id") == "2.2" and action.tool not in address_tools:
            raise ValueError(
                "Case 2.2 permits only address search and row highlighting"
            )
        if action.tool in address_tools and state.get("case_id") != "2.2":
            raise ValueError("Select --case 2.2 for address search")
        async with httpx.AsyncClient(timeout=30) as http:
            sheets = client_for_case(http, state.get("case_id"))
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
        if action.tool in address_tools or action.tool == person_tool:
            return {
                "decision": None,
                "observations": [*state["observations"], observation],
                "status": "completed"
                if result.get("stored_verified", result.get("verified", True))
                else "failed",
                "response": address_result_message(result),
            }
        if action.tool == "find_and_highlight_name":
            return {
                "decision": None,
                "observations": [*state["observations"], observation],
                "status": "completed" if result["verified"] else "failed",
                "response": result_message(result),
            }
        return {"decision": None, "observations": [*state["observations"], observation]}
    except (SheetsError, ValueError) as exc:
        return {
            "status": "failed",
            "decision": None,
            "response": (
                "User-sheet lookup failed. "
                if state.get("case_id") in {"4.2", "6.2"}
                else "Address search/highlight failed; formatting may have been applied. "
                if state.get("case_id") in {"2.2", "2.3", "4.3", "6.3"}
                else "Stopped after a tool failure. Earlier edits may have completed. "
            )
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

"""Admin-only, stateless AX768 product API. Google credentials stay in Agent Server."""
import re
from datetime import datetime, timezone
from time import monotonic
from typing import Literal
from uuid import UUID, uuid4, uuid5

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.chat.config import get_chat_settings
from app.identity.router import require_admin

router = APIRouter(prefix="/api/ax768", tags=["ax768"], dependencies=[Depends(require_admin)])
# Agent Server graph-default namespace (langgraph_api.graph.NAMESPACE_GRAPH).
AX768_ASSISTANT_ID = str(uuid5(UUID("6ba7b821-9dad-11d1-80b4-00c04fd430c8"), "ax768"))
CaseId = Literal["1.1", "2.2", "2.3", "4.2", "4.3", "6.2", "6.3", "imei"]


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    case_id: CaseId
    message: str = Field(min_length=1, max_length=8000)


def text(value, limit=8000):
    return value[:limit] if isinstance(value, str) else None


def positive_int(value):
    return value if type(value) is int and value > 0 else None


def normalize_result(payload, case_id):
    if not isinstance(payload, dict) or payload.get("status") not in {"completed", "blocked", "failed"}:
        raise ValueError("Invalid AX768 result")
    if not isinstance(payload.get("response"), str):
        raise ValueError("Missing AX768 response")
    observations = payload.get("observations", [])
    if not isinstance(observations, list):
        raise ValueError("Invalid AX768 observations")
    receipts = [item for item in observations if isinstance(item, dict)]
    last = next((item for item in reversed(receipts) if item.get("tool") != "metadata"), {})
    result = last.get("result") or {}
    if not isinstance(result, dict):
        raise ValueError("Invalid AX768 receipt")
    state = payload["status"]
    operation = result.get("status")
    allowed = {"found", "not_found", "highlighted", "highlighted_with_warnings"}
    if case_id == "imei":
        allowed = {"not_found", "connected", "disconnected"}
    outcome = state if state != "completed" else operation
    if state == "completed" and operation not in allowed:
        raise ValueError("Missing AX768 completion receipt")
    # Defensive: a successful write receipt alone is insufficient for highlight completion.
    if operation in {"highlighted", "highlighted_with_warnings"}:
        if result.get("stored_verified", result.get("verified")) is not True:
            state, outcome = "failed", "failed"
    spreadsheet = result.get("spreadsheet_id")
    if not spreadsheet:
        for item in receipts:
            metadata = item.get("result")
            if item.get("tool") == "metadata" and isinstance(metadata, dict):
                spreadsheet = metadata.get("spreadsheetId")
                break
    row = positive_int(result.get("selected_row"))
    gid = result.get("sheet_id")
    link = None
    if (isinstance(spreadsheet, str) and re.fullmatch(r"[A-Za-z0-9_-]+", spreadsheet)
            and type(gid) is int and gid >= 0 and row):
        link = f"https://docs.google.com/spreadsheets/d/{spreadsheet}/edit#gid={gid}&range=A{row}"
    args = last.get("arguments") if isinstance(last.get("arguments"), dict) else {}
    attempts = []
    for item in result.get("attempts", []) if isinstance(result.get("attempts"), list) else []:
        if isinstance(item, dict) and item.get("status") in {"found", "not_found", "failed"}:
            attempts.append({"city": text(item.get("city"), 80),
                             "sheet_alias": text(item.get("sheet_alias"), 80), "status": item["status"]})
    matches = []
    for item in result.get("matches", []) if isinstance(result.get("matches"), list) else []:
        if not isinstance(item, dict) or not positive_int(item.get("row")):
            continue
        cells = item.get("cells", [])
        if not isinstance(cells, list):
            continue
        matches.append({"row": item["row"], "cells": [
            {"cell": text(c.get("cell"), 256), "address": text(c.get("address"), 1000),
             "truncated": c.get("truncated") is True} for c in cells[:10] if isinstance(c, dict)
        ]})
    ping = None
    imei = text(result.get("imei"), 15)
    if operation in {"connected", "disconnected"}:
        raw = result.get("ping")
        if (case_id != "imei" or not isinstance(raw, dict) or not imei or not re.fullmatch(r"[0-9]{15}", imei)
                or result.get("imei") != imei or not row or not link or raw.get("imei") != imei or type(raw.get("connected")) is not bool
                or raw["connected"] != (operation == "connected")
                or (raw["connected"] and raw.get("fresh") is not True)
                or not isinstance(raw.get("sn"), str) or not re.fullmatch(r"[0-9]{1,32}", raw["sn"])):
            raise ValueError("Invalid IMEI signal receipt")
        ping = {"imei": imei, "sn": raw["sn"], "connected": raw["connected"], "fresh": raw.get("fresh") is True,
                "signal_label": text(raw.get("signal_label"), 80),
                "rssi": raw.get("rssi") if type(raw.get("rssi")) in {int, float} and -200 <= raw["rssi"] <= 200 else None,
                "elapsed_ms": raw.get("elapsed_ms") if type(raw.get("elapsed_ms")) in {int, float} and 0 <= raw["elapsed_ms"] <= 300000 else None}
    overrides = result.get("overridden_cells", [])
    response_text = (f"S/N {ping['sn']} 신호 확인되었습니다." if ping["connected"] else f"S/N {ping['sn']} 전원 연결 및 기기위치 확인해주세요.") if ping else payload["response"]
    return {"case_id": case_id, "status": state, "outcome": outcome,
            "response": response_text[:24000], "city": text(result.get("city"), 80),
            "sheet_alias": text(result.get("sheet_alias"), 80),
            "sheet_title": text(result.get("sheet_title"), 100), "selected_row": row,
            "name": text(result.get("name") or args.get("name"), 100),
            "address": text(result.get("query") or args.get("address"), 200), "sheet_url": link,
            "highlighted_range": text(result.get("highlighted_range"), 256),
            "stored_verified": result.get("stored_verified", result.get("verified")) is True if operation in {"highlighted", "highlighted_with_warnings", "verification_failed"} else None,
            "visible_verified": result.get("verified") is True if operation in {"highlighted", "highlighted_with_warnings", "verification_failed"} else None,
            "overridden_cells": [x[:256] for x in overrides[:20] if isinstance(x, str)] if isinstance(overrides, list) else [],
            "overridden_cell_count": positive_int(result.get("overridden_cell_count")) or 0,
            "match_count": positive_int(result.get("total_match_count") or result.get("match_count")) or 0,
            "matches": matches[:100], "attempts": attempts[:3],
            "imei": imei, "imei_column": text(result.get("imei_column"), 2), "ping": ping}


@router.post("/runs")
async def run(body: RunInput):
    if not body.message.strip():
        raise HTTPException(422, detail="Enter a message for the selected case.")
    settings = get_chat_settings()
    started = datetime.now(timezone.utc).isoformat()
    clock = monotonic()
    run_id = str(uuid4())
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(270, connect=5, pool=5), follow_redirects=False) as client:
            # Fail closed against an older deployed graph that would still highlight.
            schema = await client.get(f"{settings.agent_server_url}/assistants/{AX768_ASSISTANT_ID}/schemas")
            schema.raise_for_status()
            schema_data = schema.json()
            if not isinstance(schema_data, dict):
                raise ValueError("Invalid AX768 schema")
            policy = schema_data.get("input_schema", {}).get("properties", {}).get("case_policy", {})
            if policy.get("const") != "search_only":
                raise HTTPException(409, detail="Restart Agent Server to enable search-only cases.")
            if body.case_id == "imei":
                capability = schema_data.get("input_schema", {}).get("properties", {}).get("imei_case_version", {})
                if capability.get("const") != "1":
                    raise HTTPException(409, detail="Restart Agent Server to enable the IMEI case.")
            response = await client.post(f"{settings.agent_server_url}/runs/wait", json={
                "assistant_id": "ax768", "input": {"case_id": body.case_id, "message": body.message.strip(), "case_policy": "search_only", **({"imei_case_version": "1"} if body.case_id == "imei" else {})},
                "on_completion": "delete", "on_disconnect": "continue",
                "config": {"recursion_limit": 32},
            })
            response.raise_for_status()
            if len(response.content) > 1_000_000:
                raise ValueError("Oversized result")
            result = normalize_result(response.json(), body.case_id)
    except (httpx.HTTPError, ValueError):
        # A network failure after dispatch cannot prove whether a Google write occurred.
        raise HTTPException(502, detail={"code": "ax768_outcome_unknown",
            "message": "The result could not be confirmed. Inspect the sheet before running again."}) from None
    return {"id": run_id, "started_at": started, "duration_ms": round((monotonic() - clock) * 1000), **result}

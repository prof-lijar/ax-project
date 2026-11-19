"""Admin product boundary for the roster → AS completion workflow."""
import re
import unicodedata
from datetime import date, datetime, timezone
from time import monotonic
from typing import Literal
from uuid import UUID, uuid4, uuid5

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.ax768 import positive_int, text
from app.ax768_member_note import normalize_member_note
from app.chat.config import get_chat_settings
from app.identity.router import require_admin

router = APIRouter(prefix="/api/ax768/workflow", tags=["ax768"], dependencies=[Depends(require_admin)])
ASSISTANT_ID = str(uuid5(UUID("6ba7b821-9dad-11d1-80b4-00c04fd430c8"), "ax768_workflow"))


class WorkflowInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    workflow_id: Literal["device_adjustment_power"]
    message: str = Field(min_length=1, max_length=8000)
    confirmed_name: str | None = Field(default=None, min_length=2, max_length=100)


def stage(value):
    if not isinstance(value, dict) or value.get("status") not in {"found", "not_found", "skipped", "failed", "needs_confirmation", "candidate"}:
        raise ValueError("Invalid lookup stage")
    result = {key: text(value.get(key), limit) for key, limit in {
        "sheet_alias": 80, "city": 80, "sheet_title": 100, "name": 100,
        "address": 1000, "reason": 1000}.items()}
    row = positive_int(value.get("row"))
    spreadsheet, gid = value.get("spreadsheet_id"), value.get("sheet_id")
    valid_source = isinstance(spreadsheet, str) and re.fullmatch(r"[A-Za-z0-9_-]+", spreadsheet) and type(gid) is int and gid >= 0
    if value["status"] in {"found", "candidate"} and not (row and valid_source and result["name"]):
        raise ValueError("Missing match evidence")
    result.update(status=value["status"], row=row, sheet_url=(
        f"https://docs.google.com/spreadsheets/d/{spreadsheet}/edit#gid={gid}&range=A{row}"
        if valid_source and row else None))
    return result


def update_receipt(value, as_row):
    if not isinstance(value, dict) or value.get("status") not in {"updated", "skipped", "failed", "unknown"}:
        raise ValueError("Invalid AS update receipt")
    row = positive_int(value.get("row"))
    changes = value.get("changes", [])
    if not isinstance(changes, list) or len(changes) > 3:
        raise ValueError("Invalid AS changes")
    normalized = []
    for change in changes:
        if not isinstance(change, dict) or change.get("column") not in {"S", "X", "Y"} or not isinstance(change.get("value"), str):
            raise ValueError("Invalid AS cell change")
        normalized.append({"column": change["column"], "value": change["value"][:200]})
    verified = value.get("verified") is True
    day = text(value.get("date"), 10)
    y_action = value.get("y_action")
    if y_action not in {None, "updated", "unchanged"}:
        raise ValueError("Invalid Y action")
    if value["status"] == "updated":
        if not verified or not row or row != as_row or not day or date.fromisoformat(day).isoformat() != day:
            raise ValueError("Missing verified AS update evidence")
        expected = [{"column": "S", "value": "처리완료"}, {"column": "X", "value": day}]
        if y_action == "updated":
            if len(normalized) != 3 or normalized[2]["column"] != "Y" or normalized[2]["value"] not in {"위치점검완료", "전원연결완료"}:
                raise ValueError("Invalid Y completion value")
            expected.append(normalized[2])
        elif y_action != "unchanged":
            raise ValueError("Missing Y policy receipt")
        if normalized != expected:
            raise ValueError("Missing S/X completion values")
    elif verified:
        raise ValueError("Unverified update marked verified")
    return {"status": value["status"], "row": row, "date": day, "changes": normalized,
            "y_action": y_action, "verified": verified, "reason": text(value.get("reason"), 1000)}


def signal_receipt(value, roster):
    if not isinstance(value, dict) or value.get("status") not in {"skipped", "failed", "connected", "disconnected"}:
        raise ValueError("Invalid signal receipt")
    status = value["status"]
    imei, column, sn = value.get("imei"), value.get("imei_column"), value.get("sn")
    if imei is not None and (not isinstance(imei, str) or not re.fullmatch(r"[0-9]{15}", imei)):
        raise ValueError("Invalid signal IMEI")
    if column is not None and column not in {"AA", "Z", "W"}:
        raise ValueError("Invalid IMEI column")
    connected, fresh = value.get("connected"), value.get("fresh")
    if status in {"connected", "disconnected"}:
        expected_column = {"uljin-users": "AA", "yeongdeok-users": "Z", "gwangmyeon-users": "W"}.get(roster["sheet_alias"])
        if (roster["status"] != "found" or not imei or column != expected_column or not expected_column
            or not isinstance(sn, str) or not re.fullmatch(r"[0-9]{1,32}", sn)
            or type(connected) is not bool or type(fresh) is not bool
            or connected != (status == "connected") or (connected and not fresh)):
            raise ValueError("Missing verified signal evidence")
    elif sn is not None or connected is not None or fresh is not None:
        raise ValueError("Unverified signal contains a connection claim")
    rssi = value.get("rssi")
    return {"status": status, "imei_column": column, "imei": imei, "sn": sn,
            "connected": connected, "fresh": fresh, "signal_label": text(value.get("signal_label"), 80),
            "rssi": rssi if type(rssi) in {int, float} and -200 <= rssi <= 200 else None,
            "reason": text(value.get("reason"), 1000)}


def member_address_matches(roster_address, member_address, sheet_alias):
    """Allow only known administrative prefixes of the resolved roster region."""
    region = {"uljin-users": "울진", "yeongdeok-users": "영덕", "gwangmyeon-users": "광명"}.get(sheet_alias)
    prefixes = {
        "울진": (("경상북도", "경북"), ("울진군",)),
        "영덕": (("경상북도", "경북"), ("영덕군",)),
        "광명": (("경기도", "경기"), ("광명시",)),
    }
    if region not in prefixes or not all(
        isinstance(v, str) and v.strip() for v in (roster_address, member_address)
    ):
        return False

    def canonical(value):
        value = unicodedata.normalize("NFKC", value).strip()
        for choices in prefixes[region]:
            value = re.sub(
                r"^(?:" + "|".join(map(re.escape, choices)) + r")\s+",
                "",
                value,
                count=1,
            )
        return re.sub(r"\s+", "", value)

    return bool(canonical(roster_address)) and canonical(roster_address) == canonical(
        member_address
    )


def member_receipt(value, roster, lookup, update, signal):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Invalid workflow member receipt")
    operation = value.get("status")
    status = "completed" if operation in {"saved", "already_present", "not_found"} else "blocked" if operation in {"blocked", "needs_confirmation"} else "failed"
    member = normalize_member_note({"status": status, "response": "", "observations": [{"tool": "member_general_note", "result": value}]})["member_note"]
    eligible_as = (lookup["status"] == "found" and update["status"] == "updated") or (lookup["status"] == "not_found" and update["status"] == "skipped")
    if signal["status"] != "connected" or not eligible_as:
        raise ValueError("Member operation before signal/AS verification")
    if not isinstance(member["note"], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2} \[현지관리자 방문\] (기기위치조정|전원연결)", member["note"]):
        raise ValueError("Invalid workflow visit note")
    date.fromisoformat(member["note"][:10])
    if update["status"] == "updated" and member["note"][:10] != update["date"]:
        raise ValueError("Member date differs from AS completion")
    compact = lambda v: re.sub(r"\s+", "", unicodedata.normalize("NFKC", v or ""))
    if not compact(roster["name"]) or compact(roster["name"]) not in compact(member["name"]) or not compact(roster["address"]) or not member_address_matches(roster["address"], member["address"], roster["sheet_alias"]):
        raise ValueError("Member identity differs from roster")
    return member


def normalize(payload):
    if not isinstance(payload, dict) or payload.get("status") not in {"completed", "disconnected", "not_found", "needs_confirmation", "blocked", "failed"}:
        raise ValueError("Invalid workflow status")
    if not isinstance(payload.get("response"), str):
        raise ValueError("Missing workflow response")
    roster, as_lookup = stage(payload.get("roster")), stage(payload.get("as_lookup"))
    as_update = update_receipt(payload.get("as_update"), as_lookup["row"])
    signal = signal_receipt(payload.get("signal"), roster)
    if as_update["status"] in {"updated", "unknown"} and signal["status"] != "connected":
        raise ValueError("AS mutation without a verified connected signal")
    if payload["status"] == "disconnected" and (signal["status"] != "disconnected" or as_update["status"] != "skipped"):
        raise ValueError("Invalid disconnected outcome")
    if "member_note" not in payload:
        raise ValueError("Missing member stage")
    member = member_receipt(payload["member_note"], roster, as_lookup, as_update, signal)
    if payload["status"] == "completed" and (not member or not member["verified"]):
        raise ValueError("Missing member completion evidence")
    if member and member["verified"] and payload["status"] != "completed":
        raise ValueError("Inconsistent workflow completion")
    parsed = payload.get("parsed", {})
    if not isinstance(parsed, dict):
        raise ValueError("Invalid parsed input")
    attempts, candidates, notices = (payload.get(key, []) for key in ("attempts", "candidates", "notices"))
    if not all(isinstance(v, list) for v in (attempts, candidates, notices)):
        raise ValueError("Invalid workflow receipts")
    return {
        "status": payload["status"], "response": payload["response"][:8000],
        "parsed": {key: text(parsed.get(key), 200) for key in ("name", "lookup_name", "address", "mode")},
        "roster": roster, "as_lookup": as_lookup, "as_update": as_update, "signal": signal, "member_note": member,
        "attempts": [{"sheet_alias": text(a.get("sheet_alias"), 80), "city": text(a.get("city"), 80), "status": a["status"]}
                     for a in attempts[:4] if isinstance(a, dict) and a.get("status") in {"found", "not_found", "failed"}],
        "candidates": [stage(c) for c in candidates[:10]],
        "notices": [n[:1000] for n in notices[:10] if isinstance(n, str)],
    }


@router.post("/runs")
async def run(body: WorkflowInput):
    if not body.message.strip():
        raise HTTPException(422, detail="Enter a request.")
    started, clock = datetime.now(timezone.utc).isoformat(), monotonic()
    url = get_chat_settings().agent_server_url
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(420, connect=5, pool=5), follow_redirects=False) as client:
            response = await client.get(f"{url}/assistants/{ASSISTANT_ID}/schemas")
            if response.status_code == 404:
                raise HTTPException(409, detail="Restart Agent Server to enable the unified workflow.")
            response.raise_for_status()
            schema = response.json()
            if not isinstance(schema, dict):
                raise ValueError("Invalid workflow schema")
            policy = schema.get("input_schema", {}).get("properties", {}).get("workflow_version", {})
            note_policy = schema.get("input_schema", {}).get("properties", {}).get("member_note_mode", {})
            if policy.get("const") != "5" or note_policy.get("const") != "prepend":
                raise HTTPException(409, detail="Restart Agent Server to enable the unified workflow.")
            response = await client.post(f"{url}/runs/wait", json={
                "assistant_id": "ax768_workflow",
                "input": {**body.model_dump(exclude={"workflow_id"}), "message": body.message.strip(), "workflow_version": "5"},
                "on_completion": "delete", "on_disconnect": "continue", "config": {"recursion_limit": 32},
            })
            response.raise_for_status()
            if len(response.content) > 1_000_000:
                raise ValueError("Oversized workflow result")
            result = normalize(response.json())
    except (httpx.HTTPError, ValueError, AttributeError, TypeError):
        raise HTTPException(502, detail="The workflow result could not be retrieved. Check the AS row and member general notes before running again.") from None
    return {"workflow_id": body.workflow_id, "id": str(uuid4()), "started_at": started, "duration_ms": round((monotonic() - clock) * 1000), **result}

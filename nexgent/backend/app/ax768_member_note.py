"""Bounded public receipt for the member general-notes Test case."""
import re
from datetime import date


def normalize_member_note(payload):
    if not isinstance(payload, dict) or payload.get("status") not in {"completed", "failed", "blocked"} or not isinstance(payload.get("response"), str):
        raise ValueError("Invalid member note result")
    observations = payload.get("observations", [])
    receipt = next((x.get("result") for x in reversed(observations) if isinstance(x, dict) and x.get("tool") == "member_general_note"), None) if isinstance(observations, list) else None
    # Parsing/version validation can block before any external member access.
    if receipt is None and payload["status"] == "blocked":
        receipt = {"status": "blocked", "member_id": None, "name": None, "address": None, "note": None, "verified": False, "candidates": []}
    if not isinstance(receipt, dict):
        raise ValueError("Missing member note receipt")
    operation = receipt.get("status")
    outcomes = {"saved": "note_saved", "already_present": "note_present", "not_found": "not_found", "needs_confirmation": "blocked", "blocked": "blocked", "failed": "failed", "unknown": "unknown"}
    if operation not in outcomes or type(receipt.get("verified")) is not bool:
        raise ValueError("Invalid member note status")
    expected = "completed" if operation in {"saved", "already_present", "not_found"} else "blocked" if operation in {"blocked", "needs_confirmation"} else "failed"
    if payload["status"] != expected:
        raise ValueError("Member note status mismatch")
    member_id = receipt.get("member_id")
    if member_id is not None and (type(member_id) is not int or not 0 < member_id < 2**53):
        raise ValueError("Invalid member id")
    for key, limit in [("name", 100), ("address", 1000), ("note", 500)]:
        value = receipt.get(key)
        if value is not None and (not isinstance(value, str) or len(value) > limit):
            raise ValueError("Invalid member note field")
    verified = receipt["verified"]
    if verified != (operation in {"saved", "already_present"}):
        raise ValueError("Missing readback verification")
    if operation in {"saved", "already_present", "unknown"} and not (member_id and receipt.get("name") and receipt.get("note")):
        raise ValueError("Missing write identity")
    if verified:
        note = receipt["note"]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2} [^\r\n]+", note):
            raise ValueError("Invalid dated note")
        date.fromisoformat(note[:10])
    candidates = receipt.get("candidates")
    if not isinstance(candidates, list) or len(candidates) > 20:
        raise ValueError("Invalid member candidates")
    safe = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or type(candidate.get("member_id")) is not int or not 0 < candidate["member_id"] < 2**53 or not isinstance(candidate.get("name"), str) or not 0 < len(candidate["name"]) <= 100 or not isinstance(candidate.get("address"), str) or len(candidate["address"]) > 1000:
            raise ValueError("Invalid member candidate")
        safe.append({key: candidate[key] for key in ("member_id", "name", "address")})
    if bool(safe) != (operation == "needs_confirmation"):
        raise ValueError("Member candidate status mismatch")
    member = {key: receipt.get(key) for key in ("status", "member_id", "name", "address", "note", "verified")}
    member["candidates"] = safe
    return {"case_id": "member_note", "status": payload["status"], "outcome": outcomes[operation], "response": payload["response"][:4000],
            "name": member["name"], "address": member["address"], "member_note": member,
            "city": None, "sheet_alias": None, "sheet_title": None, "selected_row": None, "sheet_url": None,
            "highlighted_range": None, "stored_verified": None, "visible_verified": None, "overridden_cells": [],
            "overridden_cell_count": 0, "match_count": len(safe), "matches": [], "attempts": [], "imei": None, "imei_column": None, "ping": None}

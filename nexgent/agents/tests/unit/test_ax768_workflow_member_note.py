"""Member append follows successful signal/AS and preserves partial outcomes."""

import importlib
from datetime import date

import pytest

from workflows.ax768 import workflow_member_note as member
from workflows.ax768.member_note import parse_member_note

workflow = importlib.import_module("workflows.ax768.unified_graph")


def state(message="김영호님 기기위치조정 신호확인요", *, missing_as=False):
    return {
        "message": message,
        "response": "S/N 123 신호 확인되었습니다.\nAS 처리 결과",
        "roster": {"status": "found", "name": "김영호", "address": "영덕대게로 699"},
        "signal": {"status": "connected", "connected": True, "fresh": True},
        "as_lookup": {
            "status": "not_found" if missing_as else "found",
            "row": None if missing_as else 80,
        },
        "as_update": {
            "status": "skipped" if missing_as else "updated",
            "row": None if missing_as else 80,
            "verified": not missing_as,
            "date": None if missing_as else "2026-10-28",
            "changes": [],
        },
    }


def service(monkeypatch, status="saved"):
    calls = []

    async def run(message, *, append=False):
        assert append is True
        parsed = parse_member_note(message)
        calls.append(parsed)
        return {
            "response": "메모 결과",
            "observations": [
                {
                    "result": {
                        "status": status,
                        "verified": status in {"saved", "already_present"},
                        "name": parsed["name"],
                        "address": parsed["address"],
                        "note": parsed["note"],
                        "member_id": 12,
                        "candidates": [],
                    }
                }
            ],
        }

    monkeypatch.setattr(member, "run_member_note", run)
    monkeypatch.setattr(member, "korea_today", lambda: date(2026, 11, 10))
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["기기위치조정", "전원연결", "기기 전원 연결"])
@pytest.mark.parametrize("missing_as", [True, False])
async def test_date_action_and_roster_identity(monkeypatch, action, missing_as):
    calls = service(monkeypatch)
    s = state(f"김영호님 {action} 신호확인요", missing_as=missing_as)
    result = await member.member_note_node(s)
    expected = "기기위치조정" if action == "기기위치조정" else "전원연결"
    day = "2026-11-10" if missing_as else "2026-10-28"
    assert calls == [
        {
            "name": "김영호",
            "address": "영덕대게로 699",
            "note": f"{day} [현지관리자 방문] {expected}",
            "member_id": None,
        }
    ]
    assert result["status"] == "completed"
    assert result["response"].startswith(s["response"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "completion,action",
    [("위치점검완료", "기기위치조정"), ("전원연결완료", "전원연결")],
)
async def test_signal_only_request_uses_verified_as_type(
    monkeypatch, completion, action
):
    calls = service(monkeypatch)
    s = state("김영호님 신호확인요")
    s["as_update"]["changes"] = [{"column": "Y", "value": completion}]
    assert (await member.member_note_node(s))["status"] == "completed"
    assert calls[0]["note"].endswith(action)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expected",
    [
        ("already_present", "completed"),
        ("unknown", "failed"),
        ("failed", "failed"),
        ("not_found", "blocked"),
        ("needs_confirmation", "blocked"),
    ],
)
async def test_member_failure_preserves_as_evidence(monkeypatch, status, expected):
    service(monkeypatch, status)
    s = state()
    result = await member.member_note_node(s)
    assert result["status"] == expected and result["member_note"]["status"] == status
    assert result["response"].startswith(s["response"])
    assert s["as_update"]["verified"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stage,change",
    [
        ("signal", {"status": "disconnected", "connected": False}),
        ("signal", {"fresh": False}),
        ("as_update", {"status": "unknown", "verified": False}),
        ("as_update", {"status": "failed", "verified": False}),
        ("as_update", {"row": 99}),
        ("as_lookup", {"status": "failed"}),
        ("roster", {"status": "not_found"}),
    ],
)
async def test_direct_member_node_cannot_bypass_gate(monkeypatch, stage, change):
    calls = service(monkeypatch)
    s = state()
    s[stage].update(change)
    assert (await member.member_note_node(s))["status"] == "failed"
    assert not calls


@pytest.mark.asyncio
async def test_unspecified_action_stops_without_guessing(monkeypatch):
    calls = service(monkeypatch)
    assert (
        await member.member_note_node(state("김영호님 신호확인요", missing_as=True))
    )["status"] == "blocked"
    assert not calls


@pytest.mark.asyncio
async def test_conflicting_actions_stop_before_any_io(monkeypatch):
    calls = service(monkeypatch)
    result = await workflow.graph.ainvoke(
        {"message": "김영호님 기기위치조정 및 전원연결 신호확인요"}
    )
    assert result["status"] == "blocked" and result["member_note"] is None and not calls


@pytest.mark.asyncio
async def test_old_version_and_prior_member_receipt_are_rejected():
    result = await workflow.graph.ainvoke(
        {
            "message": "김영호님 신호확인요",
            "workflow_version": "4",
            "member_note": {"status": "saved", "verified": True},
        }
    )
    assert result["status"] == "blocked" and result["member_note"] is None


def test_workflow_advertises_append_capability():
    schema = workflow.graph.get_input_jsonschema()
    assert schema["properties"]["member_note_mode"]["const"] == "append"

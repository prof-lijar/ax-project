"""Unified request acceptance, ordered handoffs, corrections and completion handoffs."""

import importlib
from types import SimpleNamespace

import httpx
import pytest
from ax_integrations import sheets_lookup
from ax_integrations.ansimk import AnsimkError
from ax_integrations.google_sheets import GoogleSheetsClient, SheetsError

from workflows.ax768.request_parser import parse_request

workflow = importlib.import_module("workflows.ax768.unified_graph")


@pytest.mark.parametrize(
    "message,name,address",
    [
        ("김순옥", "김순옥", None),
        (" 김순옥 ", "김순옥", None),
        ("김순옥 신호확인요", "김순옥", None),
        ("김순옥 신호 확인 해 주세요~", "김순옥", None),
        ("김순옥님 신호확인요.", "김순옥", None),
        ("울진북로 164 김순옥님 신호확인요.", "김순옥", "울진북로 164"),
        ("지영희님 신호확인요 & 상밤터1길 59-4(사진).", "지영희", "상밤터1길 59-4"),
        ("왕피길83-15,정영자,기기위치조정 수신확인요~", "정영자", "왕피길 83-15"),
        (
            "① 영덕군 영덕읍 영덕대게로 699김영호,기기위치조정 수신확인요~",
            "김영호",
            "영덕대게로 699",
        ),
        (
            "② 영덕군 영덕읍 영덕대게로 699김   영호,기기위치조정 수신확인요~",
            "김영호",
            "영덕대게로 699",
        ),
        (
            "3 영덕군 영덕읍 영덕대게로 699긴 영호,기기위치조정 수신확인요~",
            "긴영호",
            "영덕대게로 699",
        ),
    ],
)
def test_supplied_inputs(message, name, address):
    result = parse_request(message)
    assert (result["name"], result["address"]) == (name, address)


@pytest.mark.parametrize(
    "message",
    [
        "",
        " ",
        "이름 없는 요청",
        "후포로 158",
        "김순옥님 사진 신호확인요",
        "후포로 158 김순옥님 왕피길 83 정영자님",
        "왕피길83-15,",
        "김순옥 정영자",
        "김순옥 사진",
        "김순옥 처리완료로 변경",
    ],
)
def test_unusable_inputs_stop_before_access(message):
    with pytest.raises(ValueError):
        parse_request(message)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario", ["latest", "older", "missing", "name_only", "changed", "candidates"]
)
async def test_lookup_real_transport_get_only(monkeypatch, scenario):
    monkeypatch.setattr(sheets_lookup, "PAGE_CELLS", 4)
    pages = []
    selected = 8 if scenario == "older" else 10

    def handle(request):
        assert request.method == "GET", "Unified workflow must not write or format"
        if request.url.path.endswith("/values:batchGet"):
            assert request.url.params.get_list("ranges") == [
                f"'AS'!I{selected}",
                f"'AS'!H{selected}",
            ]
            return httpx.Response(
                200,
                json={
                    "valueRanges": [
                        {"values": [["김영호" if scenario != "changed" else "이영호"]]},
                        {"values": [["영덕대게로 699"]]},
                    ]
                },
            )
        if "/values/" in request.url.path:
            span = request.url.path.split("/values/")[1]
            pages.append(span)
            if scenario == "candidates":
                values = [["영덕대게로699", "김영호"], ["영덕대게로699", "긴영후"]]
            elif scenario == "missing" or (scenario == "older" and len(pages) == 1):
                values = [["영덕대게로699", "다른이름"], ["영덕대게로6990", "김영호"]]
            else:
                values = [
                    ["영덕대게로699", "김영호"],
                    [
                        "다른길1" if scenario == "name_only" else "영덕대게로 699",
                        "김   영호",
                    ],
                ]
            return httpx.Response(200, json={"values": values})
        return httpx.Response(
            200,
            json={
                "sheets": [
                    {
                        "properties": {
                            "sheetId": 1,
                            "title": "AS",
                            "gridProperties": {"rowCount": 10, "columnCount": 10},
                        }
                    }
                ]
            },
        )

    async def token():
        return "test"

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = GoogleSheetsClient("as-file", token, client=http)
        args = {
            "sheet_id": 1,
            "name": "긴영호" if scenario == "candidates" else "김영호",
            "address": None if scenario == "name_only" else "영덕대게로 699",
            "name_column": "I",
            "address_column": "H",
            "start_row": 7,
            "suggest_names": True,
        }
        if scenario == "changed":
            with pytest.raises(SheetsError, match="changed"):
                await sheets_lookup.lookup_person(client, **args)
            return
        result = await sheets_lookup.lookup_person(client, **args)
    assert pages[0] == "'AS'!H9:I10"
    if scenario == "missing":
        assert result["status"] == "not_found" and not result["candidates"]
    elif scenario == "candidates":
        assert result["status"] == "not_found"
        assert [(c["name"], c["row"]) for c in result["candidates"]] == [
            ("긴영후", 10),
            ("김영호", 9),
        ]
    else:
        assert result["status"] == "found" and result["row"] == selected


def mock_workflow(
    monkeypatch,
    outcomes,
    *,
    as_status="found",
    as_address="영덕대게로 699",
    candidates=None,
    truncated=False,
    correction_changed=False,
):
    calls = []

    async def update(client, match):
        return {
            "status": "updated",
            "row": match["row"],
            "verified": True,
            "date": "2026-11-10",
            "changes": [{"column": "Y", "value": "위치점검완료"}],
            "reason": "done",
        }

    async def member(message, *, append=False):
        assert append is True
        from workflows.ax768.member_note import parse_member_note

        parsed = parse_member_note(message)
        return {
            "status": "completed",
            "response": "일반 사항 저장 확인",
            "observations": [
                {
                    "tool": "member_general_note",
                    "result": {
                        "status": "saved",
                        "member_id": 12,
                        "name": parsed["name"],
                        "address": parsed["address"],
                        "note": parsed["note"],
                        "verified": True,
                        "candidates": [],
                    },
                }
            ],
        }

    monkeypatch.setattr("workflows.ax768.workflow_member_note.run_member_note", member)

    async def read_imei(client, target, match):
        return "861212072106726"

    async def ping(imei):
        return {
            "imei": imei,
            "sn": "00300016",
            "connected": True,
            "fresh": True,
            "signal_label": "보통",
            "rssi": 22,
        }

    monkeypatch.setattr(workflow, "read_roster_imei", read_imei)
    monkeypatch.setattr(
        workflow.AnsimkClient, "from_env", lambda _: SimpleNamespace(ping=ping)
    )
    monkeypatch.setattr(workflow, "complete_as_row", update)
    monkeypatch.setenv("TEST_AX768_TOKEN", "test")
    monkeypatch.setenv("AX768_CASE_2_3_SPREADSHEET", "as-file")
    monkeypatch.setattr(
        workflow, "auth_settings", lambda: (lambda _: "test", "TEST_AX768_TOKEN")
    )
    monkeypatch.setattr(
        workflow,
        "GoogleSheetsClient",
        lambda spreadsheet, *a, **kw: SimpleNamespace(key=spreadsheet),
    )
    monkeypatch.setattr(
        workflow,
        "person_sheets_client",
        lambda _: SimpleNamespace(
            key="AS",
            search_sheet_id=1,
            person_name_column="I",
            person_address_column="H",
            search_start_row=7,
        ),
    )

    async def lookup(client, **kwargs):
        key = client.key
        calls.append((key, kwargs))
        base = {
            "sheet_id": kwargs["sheet_id"],
            "sheet_title": "명부",
            "candidates": [],
            "candidates_truncated": False,
            "status": "not_found",
        }
        if key == "AS":
            if as_status == "failed":
                raise SheetsError("read failed")
            return {
                **base,
                "status": as_status,
                "row": 80 if as_status == "found" else None,
                "name": kwargs["name"],
                "address": as_address,
            }
        index = next(
            i for i, t in enumerate(workflow.USER_SHEETS) if t.spreadsheet_id == key
        )
        # A unique suggestion requires a separate exact read before AS.
        if kwargs["name"] == "김영호" and candidates:
            if correction_changed:
                return base
            return {
                **base,
                "status": "found",
                "row": 44,
                "name": "김영호",
                "address": "영덕대게로699",
            }
        status = outcomes[index]
        if status == "failed":
            raise SheetsError("read failed")
        if status == "found":
            return {
                **base,
                "status": "found",
                "row": 44,
                "name": kwargs["name"],
                "address": "영덕대게로699",
            }
        return {
            **base,
            "candidates": [
                {"row": 44 + j, "name": name, "address": "영덕대게로699"}
                for j, name in enumerate((candidates or {}).get(index, []))
            ],
            "candidates_truncated": truncated,
        }

    monkeypatch.setattr(workflow, "lookup_person", lookup)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize("index", [0, 1, 2, None])
async def test_order_and_exact_handoff(monkeypatch, index):
    calls = mock_workflow(
        monkeypatch, ["found" if i == index else "not_found" for i in range(3)]
    )
    state = await workflow.graph.ainvoke(
        {"message": "울진북로 164 김순옥님 신호확인요."}
    )
    if index is None:
        assert state["status"] == "not_found" and len(calls) == 3
        assert state["as_lookup"]["status"] == "skipped"
    else:
        assert state["status"] == "completed"
        assert [c[0] for c in calls] == [
            t.spreadsheet_id for t in workflow.USER_SHEETS[: index + 1]
        ] + ["AS"]
        assert (
            calls[-1][1]["name"] == "김순옥"
            and calls[-1][1]["address"] == "울진북로 164"
        )
        assert state["roster"]["city"] == workflow.USER_SHEETS[index].city


@pytest.mark.asyncio
@pytest.mark.parametrize("index", [0, 1, 2, None])
@pytest.mark.parametrize(
    "message", ["김순옥", "김순옥 신호확인요", "김순옥님 신호확인요."]
)
async def test_name_only_searches_rosters_in_order_then_latest_as(
    monkeypatch, index, message
):
    calls = mock_workflow(
        monkeypatch, ["found" if i == index else "not_found" for i in range(3)]
    )
    state = await workflow.graph.ainvoke({"message": message})
    count = 3 if index is None else index + 1
    assert calls[0][0] == "AS" and calls[0][1]["address"] is None
    assert [c[0] for c in calls[1:]] == [
        t.spreadsheet_id for t in workflow.USER_SHEETS[:count]
    ]
    assert all(c[1]["address"] == "영덕대게로 699" for c in calls[1:])
    assert all(c[1]["suggest_names"] is False for c in calls[1:])
    assert state["parsed"]["address"] == "영덕대게로 699"
    assert "region" not in state["parsed"]
    assert len(calls) == count + 1
    if index is None:
        assert state["status"] == "not_found"
    else:
        assert state["status"] == "completed"
        assert state["signal"]["status"] == "connected"
        assert state["roster"]["city"] == workflow.USER_SHEETS[index].city


@pytest.mark.asyncio
async def test_name_only_roster_error_stops_search(monkeypatch):
    calls = mock_workflow(monkeypatch, ["not_found", "failed", "found"])
    state = await workflow.graph.ainvoke({"message": "김순옥님 신호확인요."})
    assert state["status"] == "failed" and len(calls) == 3
    assert calls[0][0] == "AS"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "candidates,truncated,status",
    [
        ({0: ["김영호"]}, False, "completed"),
        ({0: ["김영호", "긴영후"]}, False, "needs_confirmation"),
        ({0: ["김영호"]}, True, "needs_confirmation"),
        ({0: ["김영호"], 2: ["김영호"]}, False, "needs_confirmation"),
    ],
)
async def test_unique_correction_or_ambiguity(
    monkeypatch, candidates, truncated, status
):
    calls = mock_workflow(
        monkeypatch, ["not_found"] * 3, candidates=candidates, truncated=truncated
    )
    state = await workflow.graph.ainvoke({"message": "영덕대게로699긴 영호,수신확인요"})
    assert state["status"] == status
    if status == "completed":
        assert (
            len(calls) == 5 and calls[-2][1]["name"] == calls[-1][1]["name"] == "김영호"
        )
        assert (
            state["parsed"]["name"] == "긴영호"
            and state["parsed"]["lookup_name"] == "김영호"
        )
        assert "긴영호 → 김영호" in state["notices"][0]
    else:
        assert len(calls) == 3 and state["as_lookup"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_later_exact_beats_earlier_close_name(monkeypatch):
    calls = mock_workflow(
        monkeypatch, ["not_found", "not_found", "found"], candidates={0: ["김영호"]}
    )
    state = await workflow.graph.ainvoke({"message": "영덕대게로699긴영호,수신확인요"})
    assert state["status"] == "completed" and state["parsed"]["lookup_name"] == "긴영호"
    assert len(calls) == 4 and state["roster"]["city"] == "영덕군"


@pytest.mark.asyncio
async def test_roster_failure_stops_fallback(monkeypatch):
    calls = mock_workflow(monkeypatch, ["not_found", "failed", "found"])
    state = await workflow.graph.ainvoke({"message": "영덕대게로699김영호,수신확인요"})
    assert state["status"] == "failed" and len(calls) == 2
    assert state["as_lookup"]["status"] == "skipped"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["failed", "not_found"])
async def test_as_failure_retains_matched_roster(monkeypatch, status):
    mock_workflow(monkeypatch, ["found"], as_status=status)
    state = await workflow.graph.ainvoke({"message": "영덕대게로699김영호,수신확인요"})
    assert (
        state["status"] == ("blocked" if status == "not_found" else status)
        and state["roster"]["row"] == 44
    )


@pytest.mark.asyncio
async def test_changed_suggestion_does_not_reach_as(monkeypatch):
    calls = mock_workflow(
        monkeypatch,
        ["not_found"] * 3,
        candidates={0: ["김영호"]},
        correction_changed=True,
    )
    state = await workflow.graph.ainvoke({"message": "영덕대게로699긴영호,수신확인요"})
    assert state["status"] == "failed" and len(calls) == 4


@pytest.mark.asyncio
async def test_user_confirmation_rechecks_address_and_name(monkeypatch):
    calls = mock_workflow(monkeypatch, ["found"])
    state = await workflow.graph.ainvoke(
        {"message": "영덕대게로699긴영호,수신확인요", "confirmed_name": "김영호"}
    )
    assert state["status"] == "completed"
    assert all(c[1]["name"] == "김영호" for c in calls)
    assert calls[0][1]["suggest_names"] is False
    calls.clear()
    state = await workflow.graph.ainvoke(
        {"message": "영덕대게로699긴영호,수신확인요", "confirmed_name": "아무개"}
    )
    assert state["status"] == "blocked" and not calls


@pytest.mark.asyncio
@pytest.mark.parametrize("update_status", ["updated", "failed", "unknown"])
async def test_update_runs_only_on_matched_as_and_keeps_evidence(
    monkeypatch, update_status
):
    mock_workflow(monkeypatch, ["found"])
    writes = []

    async def update(client, match):
        writes.append(match)
        return {
            "status": update_status,
            "row": match["row"],
            "verified": update_status == "updated",
            "date": "2026-11-10",
            "changes": [{"column": "Y", "value": "위치점검완료"}],
            "reason": "checked",
        }

    monkeypatch.setattr(workflow, "complete_as_row", update)
    state = await workflow.graph.ainvoke({"message": "영덕대게로699김영호,수신확인요"})
    assert len(writes) == 1 and writes[0] == state["as_lookup"]
    assert state["status"] == ("completed" if update_status == "updated" else "failed")
    assert state["roster"]["row"] == 44 and state["as_lookup"]["row"] == 80
    assert state["as_update"]["status"] == update_status


@pytest.mark.asyncio
@pytest.mark.parametrize("as_status", ["not_found", "failed"])
async def test_missing_or_failed_as_never_updates(monkeypatch, as_status):
    mock_workflow(monkeypatch, ["found"], as_status=as_status)

    async def forbidden(*args):
        pytest.fail("No update is allowed without an AS match")

    monkeypatch.setattr(workflow, "complete_as_row", forbidden)
    state = await workflow.graph.ainvoke({"message": "영덕대게로699김영호,수신확인요"})
    assert state["as_update"]["status"] == "skipped"


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["김순옥", "울진북로 164 김순옥님 신호확인요"])
@pytest.mark.parametrize(
    "outcome", ["disconnected", "api_error", "stale", "wrong_imei", "invalid_imei"]
)
async def test_signal_gate_prevents_every_as_write(monkeypatch, message, outcome):
    calls = mock_workflow(monkeypatch, ["found"])
    pings = []

    async def read_imei(*args):
        raise SheetsError("잘못된 IMEI")

    async def ping(imei):
        pings.append(imei)
        if outcome == "api_error":
            raise AnsimkError("연결 오류")
        return {
            "imei": "000000000000000" if outcome == "wrong_imei" else imei,
            "sn": "00300016",
            "connected": outcome != "disconnected",
            "fresh": outcome not in {"stale", "disconnected"},
        }

    async def forbidden(*args):
        pytest.fail("No AS write without a fresh connected signal")

    if outcome == "invalid_imei":
        monkeypatch.setattr(workflow, "read_roster_imei", read_imei)
    monkeypatch.setattr(
        workflow.AnsimkClient, "from_env", lambda _: SimpleNamespace(ping=ping)
    )
    monkeypatch.setattr(workflow, "complete_as_row", forbidden)
    result = await workflow.graph.ainvoke({"message": message})
    assert result["status"] == (
        "disconnected" if outcome == "disconnected" else "failed"
    )
    assert result["as_update"]["status"] == "skipped"
    assert len(pings) == (0 if outcome == "invalid_imei" else 1)
    assert sum(c[0] == "AS" for c in calls) == (1 if message == "김순옥" else 0)
    if outcome == "disconnected":
        assert result["response"] == "S/N 00300016 전원 연결 및 기기위치 확인해주세요."
    else:
        assert "전원 연결 및 기기위치 확인해주세요" not in result["response"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["not_found", "failed"])
async def test_name_only_missing_as_address_stops_before_rosters(monkeypatch, status):
    calls = mock_workflow(monkeypatch, ["found"], as_status=status)
    result = await workflow.graph.ainvoke({"message": "김순옥"})
    assert result["status"] == status
    assert [c[0] for c in calls] == ["AS"]
    assert result["signal"]["status"] == "skipped"
    assert result["as_update"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_connected_report_preserves_signal_when_as_update_unknown(monkeypatch):
    mock_workflow(monkeypatch, ["found"])

    async def uncertain(*args):
        return {
            "status": "unknown",
            "row": 80,
            "verified": False,
            "reason": "저장 확인 필요",
        }

    monkeypatch.setattr(workflow, "complete_as_row", uncertain)
    result = await workflow.graph.ainvoke(
        {"message": "울진북로 164 김순옥님 신호확인요"}
    )
    assert result["status"] == "failed" and result["signal"]["status"] == "connected"
    assert result["response"] == "S/N 00300016 신호 확인되었습니다.\n저장 확인 필요"
    assert result["as_update"]["status"] == "unknown"


@pytest.mark.asyncio
async def test_update_node_itself_rejects_unverified_signal(monkeypatch):
    async def forbidden(*args):
        pytest.fail("Direct node invocation must not bypass the signal gate")

    monkeypatch.setattr(workflow, "complete_as_row", forbidden)
    result = await workflow.update_node(
        {"signal": {"status": "connected", "connected": True, "fresh": False}}
    )
    assert result["status"] == "failed"


def test_signal_workflow_contract_version():
    assert (
        workflow.graph.get_input_jsonschema()["properties"]["workflow_version"]["const"]
        == "5"
    )


@pytest.mark.asyncio
async def test_name_only_blank_as_address_never_checks_a_device(monkeypatch):
    calls = mock_workflow(monkeypatch, ["found"], as_address=" ")
    result = await workflow.graph.ainvoke({"message": "김순옥"})
    assert result["status"] == "blocked" and [c[0] for c in calls] == ["AS"]
    assert result["signal"]["status"] == "skipped"
    assert result["as_update"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_new_request_cannot_reuse_previous_signal_or_update(monkeypatch):
    calls = mock_workflow(monkeypatch, ["found"])
    result = await workflow.graph.ainvoke(
        {
            "message": "",
            "signal": {"status": "connected", "connected": True, "fresh": True},
            "as_update": {"status": "updated", "verified": True},
        }
    )
    assert not calls and result["status"] == "blocked"
    assert result["signal"]["status"] == "skipped"
    assert result["as_update"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_no_as_match_still_replaces_member_notes_for_explicit_action(monkeypatch):
    mock_workflow(monkeypatch, ["found"], as_status="not_found")
    result = await workflow.graph.ainvoke(
        {"message": "영덕대게로699김영호,전원연결 수신확인요"}
    )
    assert result["status"] == "completed"
    assert result["as_update"]["status"] == "skipped"
    assert result["member_note"]["verified"] is True
    assert result["member_note"]["note"].endswith("[현지관리자 방문] 전원연결")

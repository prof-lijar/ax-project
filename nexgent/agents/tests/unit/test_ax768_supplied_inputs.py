"""Exact operator examples through the real graph using synthetic HTTP services."""

import importlib
import json
import re

import httpx
import pytest
from ax_integrations.ansimk import COOKIE, AnsimkClient
from ax_integrations.google_sheets import GoogleSheetsClient
from ax_integrations.sheets_person import column_index

workflow = importlib.import_module("workflows.ax768.unified_graph")

# Keep fixture columns independent of production policy: live headers distinguish
# S/N from IMEI, and a fixture derived from IMEI_COLUMNS would hide this bug.
ROSTER_DEVICE_COLUMNS = {
    "uljin-users": ("Z", "AA"),
    "gwangmyeon-users": ("V", "W"),
    "yeongdeok-users": ("Y", "Z"),
}

EXAMPLES = [
    ("김순옥님 신호확인요.", "김순옥", "울진북로 164", 0),
    ("울진북로 164 김순옥님 신호확인요.", "김순옥", "울진북로 164", 0),
    ("지영희님 신호확인요 & 상밤터1길 59-4(사진).", "지영희", "상밤터1길 59-4", 1),
    ("왕피길83-15,정영자,기기위치조정 수신확인요~", "정영자", "왕피길 83-15", 0),
    (
        "① 영덕군 영덕읍 영덕대게로 699김영호,기기위치조정 수신확인요~",
        "김영호",
        "영덕대게로 699",
        2,
    ),
    (
        "② 영덕군 영덕읍 영덕대게로 699김   영호,기기위치조정 수신확인요~",
        "김영호",
        "영덕대게로 699",
        2,
    ),
    (
        "영덕군 영덕읍 영덕대게로 699김   영호,기기위치조정 수신확인요~",
        "김영호",
        "영덕대게로 699",
        2,
    ),
    (
        "3 영덕군 영덕읍 영덕대게로 699긴 영호,기기위치조정 수신확인요~",
        "김영호",
        "영덕대게로 699",
        2,
    ),
]


def synthetic_services(
    monkeypatch,
    tmp_path,
    name,
    address,
    city,
    connected,
    *,
    ambiguous=False,
    missing_as=False,
    missing_member=False,
    missing_signal=False,
):
    """Use real lookup, IMEI, ping validation and AS write/readback code."""
    target = workflow.USER_SHEETS[city]
    imei = "861212072106726"
    cells = {t.spreadsheet_id: {} for t in workflow.USER_SHEETS}
    cells["test-as"] = {}
    roster = cells[target.spreadsheet_id]
    serial_column, imei_column = ROSTER_DEVICE_COLUMNS[target.alias]
    for row in (8, 9):
        roster[target.name_column + str(row)] = name
        roster[target.address_column + str(row)] = address
        roster[serial_column + str(row)] = "300016"
        roster[imei_column + str(row)] = imei if row == 9 else "invalid-old-imei"
    if ambiguous:
        roster[target.name_column + "10"] = "긴영후"
        roster[target.address_column + "10"] = address
    cells["test-as"].update(
        {
            "I78": name,
            "H78": "다른길 1",
            "I80": name,
            "H80": address,
            "C80": "기기위치 점검",
        }
    )
    if missing_as:
        cells["test-as"].clear()
    events, writes = [], []

    credential = tmp_path / "member-credentials.json"
    credential.write_text(
        json.dumps({"username": "synthetic", "password": "synthetic"})
    )
    credential.chmod(0o600)
    monkeypatch.setenv("AX768_MEMBERS_CREDENTIALS_FILE", str(credential))
    member = {
        "id": 12,
        "full_name": name,
        "address": address,
        "general_notes": "기존 메모\n보존하지 않을 줄",
    }

    def handle(request):
        if request.url.host == "dev-check.ansimk.com":
            assert request.url.path == "/api/admin/ping" and request.method == "POST"
            assert json.loads(request.content) == {"sn": imei}
            events.append("signal")
            if missing_signal:
                return httpx.Response(404, json={"detail": "Device not found"})
            return httpx.Response(
                200,
                json={
                    "imei": imei,
                    "sn": "00300016",
                    "connected": connected,
                    "fresh": connected,
                },
            )
        if request.url.host == "api.ansimk.com":
            assert (missing_as or "AS write" in events) and connected
            events.append("member access")
            if request.url.path == "/token/":
                return httpx.Response(200, json={"access": "synthetic-token"})
            if request.url.path == "/api/admin/wards/":
                return httpx.Response(
                    200,
                    json={
                        "data": [] if missing_member else [member.copy()],
                        "totalItemCount": 0 if missing_member else 1,
                    },
                )
            if request.method == "PUT":
                body = json.loads(request.content)
                assert set(body) == {"general_notes"}
                assert body["general_notes"].endswith(" [현지관리자 방문] 기기위치조정")
                assert body["general_notes"].startswith("기존 메모\n보존하지 않을 줄\n")
                member.update(body)
                events.append("member write")
            return httpx.Response(200, json={"data": member.copy()})
        assert request.url.host == "sheets.googleapis.com"
        suffix = request.url.path.split("/v4/spreadsheets/", 1)[1]
        sheet = suffix.split("/", 1)[0].split(":", 1)[0]
        assert sheet in cells
        grid = cells[sheet]
        if request.method == "POST":
            assert sheet == "test-as" and suffix.endswith(":batchUpdate")
            assert "signal" in events and connected
            body = json.loads(request.content)
            for change in body["requests"]:
                update = change["updateCells"]
                span = update["range"]
                assert span["startRowIndex"] == 79 and span["endRowIndex"] == 80
                column = {18: "S", 23: "X", 24: "Y"}[span["startColumnIndex"]]
                assert span["endColumnIndex"] == span["startColumnIndex"] + 1
                value = update["rows"][0]["values"][0]["userEnteredValue"]
                grid[column + "80"] = value.get("stringValue", value.get("numberValue"))
            writes.append(body)
            events.append("AS write")
            return httpx.Response(200, json={"replies": [{}] * len(body["requests"])})
        assert request.method == "GET"
        if suffix.endswith("/values:batchGet"):
            ranges = request.url.params.get_list("ranges")
            return httpx.Response(
                200,
                json={
                    "valueRanges": [
                        {"values": [[grid.get(r.split("!")[1], "")]]} for r in ranges
                    ]
                },
            )
        if "/values/" in suffix:
            events.append(sheet)
            match = re.fullmatch(
                r".+!([A-Z]+)(\d+):([A-Z]+)(\d+)", suffix.split("/values/", 1)[1]
            )
            assert match
            left, top, right, bottom = match.groups()
            values = []
            for row in range(int(top), int(bottom) + 1):
                values.append(
                    [
                        grid.get(chr(64 + col) + str(row), "")
                        for col in range(column_index(left), column_index(right) + 1)
                    ]
                )
            return httpx.Response(200, json={"values": values})
        gid = (
            7
            if sheet == "test-as"
            else next(
                t.sheet_id for t in workflow.USER_SHEETS if t.spreadsheet_id == sheet
            )
        )
        return httpx.Response(
            200,
            json={
                "sheets": [
                    {
                        "properties": {
                            "sheetId": gid,
                            "title": "AS" if sheet == "test-as" else "명부",
                            "gridProperties": {
                                "rowCount": 90 if sheet == "test-as" else 20,
                                "columnCount": 30,
                            },
                        }
                    }
                ]
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handle), **kw),
    )

    async def token():
        return "synthetic-token"

    monkeypatch.setenv("TEST_AX768_TOKEN", "unused")
    monkeypatch.setenv("AX768_CASE_2_3_SPREADSHEET", "test-as")
    monkeypatch.setattr(
        workflow, "auth_settings", lambda: (lambda _: token, "TEST_AX768_TOKEN")
    )
    monkeypatch.setattr(
        workflow,
        "person_sheets_client",
        lambda http: GoogleSheetsClient(
            "test-as",
            token,
            client=http,
            search_sheet_id=7,
            person_name_column="I",
            person_address_column="H",
            search_start_row=7,
        ),
    )

    def admin(http):
        http.cookies.set(
            COOKIE, "synthetic-session", domain="dev-check.ansimk.com", path="/"
        )
        return AnsimkClient(
            http,
            code_file=tmp_path / "unused-code",
            session_file=tmp_path / "unused-session",
        )

    monkeypatch.setattr(AnsimkClient, "from_env", admin)
    return events, writes, target


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "example",
    EXAMPLES,
    ids=[
        "name",
        "address-name",
        "name-photo-text",
        "comma",
        "joined",
        "spaced-name",
        "reported-spacing-failure",
        "typo",
    ],
)
@pytest.mark.parametrize("connected", [True, False], ids=["connected", "disconnected"])
@pytest.mark.parametrize("quoted", [False, True], ids=["plain", "quoted"])
async def test_exact_examples_through_signal_and_as(
    monkeypatch, tmp_path, example, connected, quoted
):
    message, name, address, city = example
    events, writes, target = synthetic_services(
        monkeypatch, tmp_path, name, address, city, connected
    )
    result = await workflow.graph.ainvoke(
        {"message": f'"{message}"' if quoted else message}
    )
    assert result["parsed"]["lookup_name"] == name
    assert result["parsed"]["address"] == address
    assert result["roster"]["row"] == 9
    assert result["signal"]["imei_column"] == ROSTER_DEVICE_COLUMNS[target.alias][1]
    assert result["signal"]["sn"] == "00300016"
    assert events.count("signal") == 1
    if example == EXAMPLES[0]:
        assert events[0] == "test-as"  # Latest AS address precedes roster lookup.
        assert result["as_lookup"]["row"] == 80
    else:
        assert events[0] == workflow.USER_SHEETS[0].spreadsheet_id
    if example == EXAMPLES[-1]:
        assert any("긴영호 → 김영호" in notice for notice in result["notices"])
    if connected:
        assert result["status"] == "completed" and len(writes) == 1
        assert result["as_lookup"]["row"] == 80
        assert result["as_update"]["verified"] is True
        assert result["member_note"]["verified"] is True
        assert (
            events.index("signal")
            < events.index("AS write")
            < events.index("member write")
        )
        assert result["response"].startswith("S/N 00300016 신호 확인되었습니다.")
    else:
        assert result["status"] == "disconnected" and not writes
        assert result["as_update"]["status"] == "skipped"
        assert result["member_note"] is None
        assert "member write" not in events
        assert result["response"] == "S/N 00300016 전원 연결 및 기기위치 확인해주세요."


@pytest.mark.asyncio
async def test_exact_typo_with_multiple_candidates_requires_confirmation(
    monkeypatch, tmp_path
):
    message, name, address, city = EXAMPLES[-1]
    events, writes, _ = synthetic_services(
        monkeypatch, tmp_path, name, address, city, True, ambiguous=True
    )
    result = await workflow.graph.ainvoke({"message": message})
    assert result["status"] == "needs_confirmation"
    assert {c["name"] for c in result["candidates"]} == {"김영호", "긴영후"}
    assert "signal" not in events and not writes


@pytest.mark.asyncio
async def test_three_numbered_lines_together_are_blocked_before_io(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Combined requests must stop before any external I/O")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    result = await workflow.graph.ainvoke(
        {"message": "\n".join(item[0] for item in EXAMPLES[-3:])}
    )
    assert result["status"] == "blocked"
    assert result["response"] == "한 번에 한 사람의 이름과 주소를 입력해 주세요."


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_as", [False, True])
@pytest.mark.parametrize("missing_member", [False, True])
async def test_optional_as_and_master_page_missing_paths(
    monkeypatch, tmp_path, missing_as, missing_member
):
    events, writes, _ = synthetic_services(
        monkeypatch,
        tmp_path,
        "정영자",
        "왕피길 83-15",
        2,
        True,
        missing_as=missing_as,
        missing_member=missing_member,
    )
    result = await workflow.graph.ainvoke(
        {"message": "왕피길83-15,정영자,기기위치조정 신호확인요"}
    )
    assert result["signal"]["status"] == "connected"
    assert len(writes) == (0 if missing_as else 1)
    assert result["as_update"]["status"] == ("skipped" if missing_as else "updated")
    assert events.index("signal") < events.index("member access")
    assert result["member_note"]["status"] == (
        "not_found" if missing_member else "saved"
    )
    assert result["status"] == ("blocked" if missing_member else "completed")
    assert ("member write" in events) is (not missing_member)
    if missing_member:
        assert "마스터페이지 일반 사항:" in result["response"]
        assert "가입자가 없어" in result["response"]
    if missing_as:
        assert "AS시트에서 일치하는 행을 찾지 못해" in result["response"]


@pytest.mark.asyncio
async def test_signal_device_not_found_skips_all_writers(monkeypatch, tmp_path):
    events, writes, _ = synthetic_services(
        monkeypatch,
        tmp_path,
        "정영자",
        "왕피길 83-15",
        1,
        True,
        missing_signal=True,
    )
    result = await workflow.graph.ainvoke(
        {"message": "왕피길83-15,정영자,기기위치조정 신호확인요"}
    )
    assert result["signal"]["status"] == "failed"
    assert result["as_lookup"]["status"] == "skipped"
    assert result["as_update"]["status"] == "skipped"
    assert result["member_note"] is None
    assert "test-as" not in events and "member access" not in events and not writes
    assert any("일반 사항 저장을 건너뛰었습니다" in n for n in result["notices"])

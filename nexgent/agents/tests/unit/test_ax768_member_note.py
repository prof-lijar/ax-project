"""Member-note writes replace the entire field and stop on identity/verification uncertainty."""

import importlib
import json

import httpx
import pytest
from ax_integrations.ansimk_members import AnsimkMembersClient, MembersError

from workflows.ax768.member_note import parse_member_note, run_member_note

NOTE = "2026-10-28 [현지관리자 방문] 기기위치조정"
MESSAGE = f"이름: 이은경\n일반 사항: {NOTE}"


@pytest.mark.parametrize(
    "message",
    [
        "이은경",
        "이름: 이은경",
        MESSAGE + "\n이름: 다른사람",
        MESSAGE.replace("2026-10-28", "2026-02-30"),
        MESSAGE + "\n가입자 ID: -1",
        MESSAGE + "\n삭제: 모두",
        MESSAGE.replace(NOTE, "x" * 501),
    ],
)
def test_reject_invalid_input(message):
    with pytest.raises(ValueError):
        parse_member_note(message)


def test_keep_explicit_date_and_normalize_only_identity_spacing():
    result = parse_member_note(
        MESSAGE.replace("이은경", "넥스터_이 은경") + "\n가입자 ID: 12"
    )
    assert (
        result["name"] == "넥스터_이 은경"
        and result["note"] == NOTE
        and result["member_id"] == 12
    )


def service(monkeypatch, tmp_path, scenario):
    credential = tmp_path / "credentials.json"
    credential.write_text(json.dumps({"username": "test", "password": "secret-test"}))
    credential.chmod(0o600)
    monkeypatch.setenv("AX768_MEMBERS_CREDENTIALS_FILE", str(credential))
    row = {
        "id": 12,
        "full_name": "넥스터_이은경"
        if scenario in {"partial", "multiple_partial"}
        else "이은경",
        "address": "테스트로 1",
        "general_notes": "기존 기록\n",
    }
    if scenario == "duplicate":
        row["general_notes"] = NOTE
    if scenario == "contains":
        row["general_notes"] += NOTE
    if scenario == "overflow":
        row["general_notes"] = "x" * 1999
    reads, writes = [], []

    def handle(request):
        assert request.url.host == "api.ansimk.com"
        if request.url.path == "/token/":
            assert request.method == "POST" and json.loads(request.content) == {
                "username": "test",
                "password": "secret-test",
            }
            return httpx.Response(200, json={"access": "fake-token"})
        assert request.headers["Authorization"] == "Bearer fake-token"
        if request.url.path == "/api/admin/wards/":
            assert request.method == "GET"
            items = [] if scenario == "missing" else [row.copy()]
            if scenario in {"multiple", "multiple_partial"}:
                items.append({**row, "id": 13, "address": "다른길 2"})
            if scenario == "exact_preferred":
                items.append({**row, "id": 13, "full_name": "넥스터_이은경"})
            return httpx.Response(
                200, json={"data": items, "totalItemCount": len(items), "totalPages": 1}
            )
        if request.method == "PUT":
            assert request.url.path == "/api/admin/wards/12/update/"
            body = json.loads(request.content)
            assert body == {"general_notes": NOTE}
            writes.append(body)
            if scenario == "rejected":
                return httpx.Response(403, json={})
            row.update(body)
            if scenario == "timeout":
                raise httpx.ReadTimeout("sensitive internal detail")
            return httpx.Response(200, json={"data": row})
        assert request.method == "GET" and request.url.path == "/api/admin/wards/12/"
        reads.append(True)
        result = row.copy()
        if scenario == "changed" and len(reads) == 2:
            result["general_notes"] += "다른 편집"
        if scenario == "identity":
            result["full_name"] = "다른사람"
        if scenario == "mismatch" and writes:
            result["general_notes"] = "unexpected"
        if scenario == "readback_error" and writes:
            return httpx.Response(500, json={})
        return httpx.Response(200, json={"data": result})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs),
    )
    return reads, writes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario,status,writes_expected",
    [
        ("saved", "saved", 1),
        ("duplicate", "already_present", 0),
        ("missing", "not_found", 0),
        ("partial", "saved", 1),
        ("multiple_partial", "needs_confirmation", 0),
        ("exact_preferred", "saved", 1),
        ("contains", "saved", 1),
        ("multiple", "needs_confirmation", 0),
        ("changed", "failed", 0),
        ("identity", "failed", 0),
        ("overflow", "saved", 1),
        ("rejected", "failed", 1),
        ("timeout", "unknown", 1),
        ("mismatch", "unknown", 1),
        ("readback_error", "unknown", 1),
    ],
)
async def test_replacement_boundaries(
    monkeypatch, tmp_path, scenario, status, writes_expected
):
    reads, writes = service(monkeypatch, tmp_path, scenario)
    result = await run_member_note(MESSAGE)
    receipt = result["observations"][0]["result"]
    assert receipt["status"] == status and len(writes) == writes_expected
    assert receipt["verified"] == (status in {"saved", "already_present"})
    assert (
        "secret-test" not in str(result)
        and "fake-token" not in str(result)
        and "기존 기록" not in str(result)
    )
    if status == "saved":
        assert len(reads) == 3
    if status == "unknown":
        assert "재실행 전에" in result["response"]


@pytest.mark.asyncio
async def test_repeat_is_idempotent_and_explicit_id_disambiguates(
    monkeypatch, tmp_path
):
    _, writes = service(monkeypatch, tmp_path, "multiple")
    for _ in range(2):
        result = await run_member_note(MESSAGE + "\n가입자 ID: 12")
        assert result["status"] == "completed"
    assert len(writes) == 1


@pytest.mark.asyncio
async def test_graph_routes_without_google_or_model_and_requires_capability(
    monkeypatch, tmp_path
):
    service(monkeypatch, tmp_path, "saved")
    graph = importlib.import_module("workflows.ax768.graph")

    def forbidden(*args, **kwargs):
        pytest.fail("Member case must not use Google or model")

    monkeypatch.setattr(graph, "auth_settings", forbidden)
    result = await graph.graph.ainvoke({"case_id": "member_note", "message": MESSAGE})
    assert result["status"] == "blocked"
    result = await graph.graph.ainvoke(
        {"case_id": "member_note", "member_note_case_version": "2", "message": MESSAGE}
    )
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_private_credentials_required(tmp_path):
    p = tmp_path / "credentials.json"
    p.write_text('{"username":"test","password":"test"}')
    p.chmod(0o644)
    async with httpx.AsyncClient() as http:
        with pytest.raises(MembersError, match="600"):
            await AnsimkMembersClient(http, p).login()


@pytest.mark.asyncio
async def test_search_reads_all_pages_and_rejects_incomplete_results():
    calls = []

    def handle(request):
        page = int(request.url.params["page"])
        calls.append(page)
        rows = [{"id": i} for i in (range(1, 51) if page == 1 else [51])]
        return httpx.Response(200, json={"data": rows, "totalItemCount": 51})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        rows = await AnsimkMembersClient(http, "unused").search("이은경")
    assert len(rows) == 51 and calls == [1, 2]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "conditions,expected",
    [
        ("\n주소: 테스트로 1", "saved"),
        ("\n가입자 ID: 12", "saved"),
        ("\n주소: 다른길 2", "not_found"),
        ("\n가입자 ID: 13", "not_found"),
    ],
)
async def test_unique_partial_respects_explicit_conditions(
    monkeypatch, tmp_path, conditions, expected
):
    _, writes = service(monkeypatch, tmp_path, "partial")
    result = await run_member_note(MESSAGE + conditions)
    assert result["observations"][0]["result"]["status"] == expected
    assert len(writes) == (expected == "saved")


@pytest.mark.asyncio
async def test_old_append_capability_cannot_dispatch_replacement(monkeypatch, tmp_path):
    _, writes = service(monkeypatch, tmp_path, "saved")
    graph = importlib.import_module("workflows.ax768.graph")
    result = await graph.graph.ainvoke(
        {"case_id": "member_note", "member_note_case_version": "1", "message": MESSAGE}
    )
    assert result["status"] == "blocked"
    assert not writes

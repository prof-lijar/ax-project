"""Information updates: identity, bounded writes and failure ordering."""

from copy import deepcopy
from datetime import date

import pytest
from ax_integrations.google_sheets import SheetsError

from workflows.ax768 import information_update as flow
from workflows.ax768.information_policy import (
    GuardianChange,
    InformationPlan,
    grounded_plan,
)
from workflows.ax768.information_sheets import (
    AS_LAYOUT,
    LAYOUTS,
    Table,
    resolve_roster,
    roster_changes,
    select_as,
)


def plan(**kw):
    return (
        InformationPlan(
            name="김하늘",
            address="테스트길 10",
            current_phone="",
            birthday="380215",
            new_phone="",
            guardian=None,
            visit_date="",
            memo="",
            blocked_reason="",
            **kw,
        )
        if not kw
        else InformationPlan.model_validate({**plan().model_dump(), **kw})
    )


def person(row=6, phone="010-0000-1111", address="테스트길 10"):
    return {"row": row, "name": "김하늘", "address": address, "phone": phone}


def test_grounding_preserves_zero_and_separates_numbers():
    p = plan(
        birthday="030215", new_phone="010-0000-2222", current_phone="010-0000-1111"
    )
    assert (
        grounded_plan(
            p,
            "김하늘 테스트길 10 기존 010-0000-1111 새 010-0000-2222 생년월일030215로수정",
        ).birthday
        == "030215"
    )
    with pytest.raises(ValueError):
        grounded_plan(p, "김하늘 테스트길 10")
    with pytest.raises(ValueError):
        grounded_plan(
            plan(new_phone="010-0000-1111", current_phone="010-0000-1111"),
            "김하늘 테스트길 10 380215 010-0000-1111",
        )
    with pytest.raises(ValueError):
        plan(birthday="381332")


def test_roster_ambiguity_never_updates_all_and_as_fallback_disambiguates():
    p = plan(address="")
    a, b = person(), person(7, "010-0000-2222", "다른길 5")
    with pytest.raises(ValueError):
        resolve_roster(p, [a, b], [])
    assert resolve_roster(p, [a, b], [person(10)]) == a
    with pytest.raises(ValueError):
        resolve_roster(p, [a, a], [person(10)])
    # Even if the AS matches, an explicit conflicting current number cannot be ignored.
    with pytest.raises(ValueError):
        resolve_roster(plan(current_phone="010-0000-9999"), [a], [person(10)])


def test_as_same_name_and_current_phone_all_rows_only():
    a = person()
    rows = [person(8), person(9), person(10, "010-0000-3333")]
    assert [r["row"] for r in select_as(rows, a)] == [8, 9]
    assert select_as([], a) == []
    with pytest.raises(ValueError):
        select_as([person(8, ""), person(9, "")], a)
    with pytest.raises(ValueError):
        select_as([person(8, "010-0000-3333")], a)


def before_roster(region="영덕"):
    l = LAYOUTS[region]
    cols = [l.name, l.address, l.phone, l.birthday] + [
        c for slot in l.guardians for c in slot
    ]
    values = {c + "6": "" for c in cols}
    values.update(
        {
            l.name + "6": "김하늘",
            l.address + "6": "테스트길 10",
            l.phone + "6": "010-0000-1111",
            l.birthday + "6": "380214",
        }
    )
    return values


def test_guardian_add_preserves_existing_and_uses_empty_slot():
    l = LAYOUTS["영덕"]
    before = before_roster()
    before.update(Q6="기존보호자", R6="010-0000-5555", S6="아들")
    p = plan(
        guardian=GuardianChange(
            mode="add",
            current_phone="",
            name="",
            relationship="며느님",
            phone="010-0000-6666",
        )
    )
    changes = roster_changes(p, l, 6, before)
    assert (6, "U", "010-0000-6666", False) in changes
    assert (6, "V", "며느님", False) in changes
    assert not any(c in {"Q", "R", "S"} for _, c, _, _ in changes)
    before.update(U6="010-0000-6666", V6="며느님")
    assert roster_changes(p, l, 6, before) == [(6, "E", "380215", False)]
    before.update(U6="010-0000-7777")
    with pytest.raises(ValueError):
        roster_changes(p, l, 6, before)


def test_guardian_replace_requires_existing_unique_phone():
    p = plan(
        guardian=GuardianChange(
            mode="replace",
            current_phone="010-0000-5555",
            name="새보호자",
            relationship="딸",
            phone="010-0000-6666",
        )
    )
    before = before_roster()
    before.update(R6="010-0000-5555", S6="아들")
    assert (6, "Q", "새보호자", False) in roster_changes(p, LAYOUTS["영덕"], 6, before)
    before["U6"] = "010-0000-5555"
    with pytest.raises(ValueError):
        roster_changes(p, LAYOUTS["영덕"], 6, before)
    before = before_roster()
    before["E6"] = "=D6"
    with pytest.raises(ValueError):
        roster_changes(plan(), LAYOUTS["영덕"], 6, before)


class FakeTable:
    def __init__(self, layout, rows, values, log, fail=False):
        self.layout, self.rows, self.values, self.log, self.fail = (
            layout,
            rows,
            values,
            log,
            fail,
        )

    async def initialize(self):
        pass

    async def check_headers(self):
        pass

    async def find(self, name, information_only=False):
        return deepcopy(self.rows)

    async def snapshot(self, row, cols):
        return {
            f"{c}{row}": self.values.get(f"{c}{row}", "") for c in dict.fromkeys(cols)
        }

    async def cells(self, addresses, render):
        return {a: self.values.get(a, "") for a in addresses}

    async def write(self, before, changes):
        assert await self.cells(list(before), "FORMULA") == before
        self.log.append(("AS" if self.layout == AS_LAYOUT else "roster", changes))
        self.values.update({f"{c}{r}": v for r, c, v, _ in changes})
        if self.fail:
            raise SheetsError("readback failed")


class FakeMember:
    def __init__(self, log, fail=False):
        self.log, self.fail = log, fail
        self.row = {
            "id": 12,
            "full_name": "김하늘",
            "address": "테스트길 10",
            "general_notes": "2026-10-01 기존 메모",
        }

    async def login(self):
        pass

    async def search(self, name):
        return [deepcopy(self.row)]

    async def detail(self, id):
        return deepcopy(self.row)

    async def write_notes(self, id, notes):
        self.log.append(("member", notes))
        self.row["general_notes"] = notes
        if self.fail:
            raise flow.MembersError("dispatched timeout")


def setup(
    monkeypatch,
    *,
    as_rows=None,
    fail_roster=False,
    fail_as=False,
    fail_member=False,
    p=None,
):
    log = []
    r = FakeTable(LAYOUTS["영덕"], [person()], before_roster(), log, fail_roster)
    rows = as_rows if as_rows is not None else [person(8), person(9)]
    av = {}
    for a in rows:
        n = a["row"]
        av.update(
            {
                f"{c}{n}": v
                for c, v in [
                    ("I", a["name"]),
                    ("H", a["address"]),
                    ("K", a["phone"]),
                    ("C", "정보확인"),
                    ("E", "영덕"),
                    ("S", "진행중"),
                    ("X", ""),
                    ("Y", ""),
                ]
            }
        )
    a = FakeTable(AS_LAYOUT, rows, av, log, fail_as)
    m = FakeMember(log, fail_member)

    async def prepare(message):
        return p or plan(new_phone="010-0000-2222")

    monkeypatch.setattr(flow, "prepare_plan", prepare)
    monkeypatch.setattr(
        flow,
        "tables",
        lambda http, region: (
            r if region == "영덕" else FakeTable(LAYOUTS[region], [], {}, log),
            a,
        ),
    )
    monkeypatch.setattr(flow.AnsimkMembersClient, "from_env", lambda http: m)
    monkeypatch.setattr(flow, "korea_today", lambda: date(2026, 11, 12))
    return log, r, a, m


@pytest.mark.asyncio
async def test_full_workflow_uses_old_phone_for_all_as_rows_and_appends_note(
    monkeypatch,
):
    log, r, a, m = setup(monkeypatch)
    result = await flow.graph.ainvoke({"information_version": "2", "message": "test"})
    assert result["status"] == "completed"
    assert [item[0] for item in log] == ["roster", "AS", "member"]
    assert r.values["O6"] == "010-0000-2222"
    for row in [8, 9]:
        assert a.values[f"Y{row}"] == "정보확인완료"
        assert a.values[f"S{row}"] == "처리완료"
        assert a.values[f"X{row}"] == (date(2026, 11, 12) - date(1899, 12, 30)).days
        assert a.values[f"K{row}"] == "010-0000-1111"
    assert m.row["general_notes"].startswith(
        "2026-10-01 기존 메모\n2026-11-12 [현지관리자 방문] 정보확인/생년월일 380215로 수정"
    )
    assert result["receipts"]["as_update"]["rows"] == [8, 9]


@pytest.mark.asyncio
async def test_missing_as_is_verified_skip_and_member_still_runs(monkeypatch):
    log, *_ = setup(monkeypatch, as_rows=[])
    result = await flow.graph.ainvoke({"information_version": "2", "message": "test"})
    assert result["status"] == "completed"
    assert [item[0] for item in log] == ["roster", "member"]
    assert result["receipts"]["as_update"]["status"] == "skipped"
    assert result["receipts"]["as_update"]["verified"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failed,stages",
    [
        ("roster", ["roster"]),
        ("as", ["roster", "AS"]),
        ("member", ["roster", "AS", "member"]),
    ],
)
async def test_uncertain_write_stops_dependent_stages_without_retry(
    monkeypatch, failed, stages
):
    log, *_ = setup(monkeypatch, **{f"fail_{failed}": True})
    result = await flow.graph.ainvoke({"information_version": "2", "message": "test"})
    assert result["status"] == "failed"
    assert [item[0] for item in log] == stages
    assert (
        result["receipts"][
            {"as": "as_update", "member": "member_note"}.get(failed, failed)
        ]["status"]
        == "unknown"
    )


@pytest.mark.asyncio
async def test_stale_version_never_reaches_tools(monkeypatch):
    log, *_ = setup(monkeypatch)
    result = await flow.graph.ainvoke({"information_version": "1", "message": "test"})
    assert result["status"] == "blocked" and log == []


@pytest.mark.asyncio
async def test_note_retry_deduplicates_and_preserves_previous_entries(monkeypatch):
    log, _r, _a, m = setup(monkeypatch, p=plan())
    value = {"information_version": "2", "message": "test"}
    assert (await flow.graph.ainvoke(value))["status"] == "completed"
    saved = m.row["general_notes"]
    log.clear()
    assert (await flow.graph.ainvoke(value))["status"] == "completed"
    assert log == [] and m.row["general_notes"] == saved


@pytest.mark.asyncio
async def test_table_write_checks_readback_and_exact_updatecells_mask():
    class Client:
        async def _request(self, method, suffix, **kw):
            if method == "POST":
                assert suffix == ":batchUpdate"
                cells = kw["json"]["requests"]
                assert len(cells) == 1
                assert cells[0]["updateCells"]["fields"] == "userEnteredValue"
                assert cells[0]["updateCells"]["rows"][0]["values"][0][
                    "userEnteredValue"
                ] == {"stringValue": "030215"}
                return {}
            return {"valueRanges": [{"values": [["김하늘"]]}, {"values": [["030215"]]}]}

    table = Table(Client(), 12, 6, LAYOUTS["영덕"])
    table.title = "'영덕'"
    await table.write({"C6": "김하늘", "E6": "380214"}, [(6, "E", "030215", False)])
    with pytest.raises(SheetsError):
        await table.write(
            {"C6": "다른사람", "E6": "380214"}, [(6, "E", "030215", False)]
        )


def test_same_name_as_for_other_subscriber_is_skipped():
    assert select_as([person(10, "010-0000-9999", "다른길 12")], person()) == []


@pytest.mark.asyncio
async def test_header_drift_blocks_before_any_mutation():
    class Client:
        async def _request(self, method, suffix, **kw):
            assert method == "GET"
            return {
                "valueRanges": [
                    {"values": [["changed"]]} for _ in kw["params"]["ranges"]
                ]
            }

    table = Table(Client(), 12, 6, LAYOUTS["영덕"])
    table.title = "'영덕'"
    with pytest.raises(SheetsError):
        await table.check_headers()


@pytest.mark.asyncio
async def test_snapshot_drift_stops_before_write(monkeypatch):
    log, r, _, _ = setup(monkeypatch)
    original = r.check_headers

    async def drift():
        await original()
        r.values["C6"] = "다른사람"

    r.check_headers = drift
    result = await flow.graph.ainvoke({"information_version": "2", "message": "test"})
    assert result["status"] == "blocked" and log == []


@pytest.mark.asyncio
async def test_member_ambiguity_keeps_sheet_receipts(monkeypatch):
    log, _, _, m = setup(monkeypatch)

    async def duplicate(name):
        return [m.row, {**m.row, "id": 13}]

    m.search = duplicate
    result = await flow.graph.ainvoke({"information_version": "2", "message": "test"})
    assert result["status"] == "blocked"
    assert [s[0] for s in log] == ["roster", "AS"]
    assert (
        result["receipts"]["roster"]["verified"]
        and result["receipts"]["as_update"]["verified"]
    )


@pytest.mark.asyncio
async def test_as_lookup_filters_issue_and_name_without_dropping_blank_region():
    class Client:
        async def _request(self, method, suffix, **kw):
            assert method == "GET"
            ranges = kw["params"]["ranges"]
            if ranges == ["'AS'!I7:I9"]:
                return {
                    "valueRanges": [{"values": [["김하늘"], ["김하늘"], ["다른사람"]]}]
                }
            assert ranges == [
                f"'AS'!{col}{row}" for row in [7, 8] for col in ["I", "H", "K", "C"]
            ]
            return {
                "valueRanges": [
                    {"values": [[value]]}
                    for value in [
                        "김하늘",
                        "테스트길 10",
                        "010-0000-1111",
                        "정보확인",
                        "김하늘",
                        "테스트길 10",
                        "010-0000-1111",
                        "기기전원 연결",
                    ]
                ]
            }

    table = Table(Client(), 12, 7, AS_LAYOUT)
    table.title = "'AS'"
    table.end = 9
    assert await table.find("김하늘", information_only=True) == [person(7)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "found_region, expected",
    [
        ("울진", ["울진"]),
        ("광명", ["울진", "광명"]),
        ("영덕", ["울진", "광명", "영덕"]),
    ],
)
async def test_sequential_rosters_stop_at_first_resolved_match(
    monkeypatch, found_region, expected
):
    visited = []
    cases = FakeTable(AS_LAYOUT, [], {}, [])

    def factory(http, region):
        visited.append(region)
        return FakeTable(
            LAYOUTS[region], [person()] if region == found_region else [], {}, []
        ), cases

    monkeypatch.setattr(flow, "tables", factory)
    region, _, _, selected, _ = await flow.find_roster(None, plan())
    assert region == found_region and selected == person()
    assert visited == expected


@pytest.mark.asyncio
async def test_no_match_checks_all_three_without_writes(monkeypatch):
    visited = []
    log = []

    def factory(http, region):
        visited.append(region)
        return FakeTable(
            LAYOUTS[region], [person(address="다른길 5")], {}, log
        ), FakeTable(AS_LAYOUT, [], {}, log)

    monkeypatch.setattr(flow, "tables", factory)
    with pytest.raises(ValueError, match="세 지역"):
        await flow.find_roster(None, plan())
    assert visited == ["울진", "광명", "영덕"] and log == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["ambiguous", "read_error"])
async def test_ambiguity_or_read_failure_does_not_skip_to_another_roster(
    monkeypatch, failure
):
    visited = []
    roster = FakeTable(LAYOUTS["울진"], [person(), person(7)], {}, [])
    if failure == "read_error":

        async def fail():
            raise SheetsError("read failed")

        roster.initialize = fail

    def factory(http, region):
        visited.append(region)
        return roster, FakeTable(AS_LAYOUT, [], {}, [])

    monkeypatch.setattr(flow, "tables", factory)
    with pytest.raises((ValueError, SheetsError)):
        await flow.find_roster(None, plan())
    assert visited == ["울진"]


@pytest.mark.asyncio
async def test_roster_read_error_identifies_sheet_and_cause(monkeypatch):
    log, roster, _, _ = setup(monkeypatch)

    async def fail():
        raise SheetsError("Google response exceeded the data limit; narrow the range")

    roster.initialize = fail
    result = await flow.graph.ainvoke({"information_version": "2", "message": "test"})
    assert result["status"] == "blocked" and log == []
    assert "영덕 명부" in result["response"] and "허용 크기" in result["response"]
    assert "보호자 빈 칸" not in result["response"]


def test_roster_error_does_not_expose_raw_validation_input():
    with pytest.raises(ValueError) as caught:
        plan(birthday="private-invalid-input")
    reason = flow.stage_failure_reason(caught.value, "가입자 조회")
    assert "private-invalid-input" not in reason
    assert "private-key" not in flow.stage_failure_reason(
        KeyError("private-key"), "가입자 조회"
    )


@pytest.mark.parametrize(
    "roster,master,region,expected",
    [
        ("영해면 대동로 1549", "영덕군 영해면 대동로 1549", "영덕", True),
        ("영해면 대동로 1549", "경상북도 영덕군 영해면 대동로 1549", "영덕", True),
        ("경북 영덕군 영해면 대동로 1549", "영해면 대동로 1549", "영덕", True),
        ("후포면 테스트길 10", "경북 울진군 후포면 테스트길 10", "울진", True),
        ("테스트로 10", "경기도 광명시 테스트로 10", "광명", True),
        ("영해면 대동로 1549", "울진군 영해면 대동로 1549", "영덕", False),
        (
            "영해면 대동로 1549",
            "강원특별자치도 영덕군 영해면 대동로 1549",
            "영덕",
            False,
        ),
        ("영해면 대동로 1549", "영덕군 영해면 대동로 15490", "영덕", False),
        ("영해면 대동로 1549", "영덕군 영해면 대동로 1549 101호", "영덕", False),
        ("영해면 대동로 1549", "영덕군길 영해면 대동로 1549", "영덕", False),
        ("", "영덕군", "영덕", False),
    ],
)
def test_member_address_only_normalizes_known_region_prefixes(
    roster, master, region, expected
):
    assert flow.member_address_matches(roster, master, region) is expected


@pytest.mark.asyncio
async def test_member_region_prefix_matches_and_preserves_full_master_identity(
    monkeypatch,
):
    log, _, _, m = setup(monkeypatch)
    m.row["address"] = "경상북도 영덕군 테스트길 10"
    result = await flow.graph.ainvoke({"information_version": "2", "message": "test"})
    assert result["status"] == "completed"
    assert m.row["address"] == "경상북도 영덕군 테스트길 10"
    assert m.row["general_notes"].startswith("2026-10-01 기존 메모\n")
    assert [s[0] for s in log] == ["roster", "AS", "member"]


@pytest.mark.asyncio
async def test_member_prefix_equivalent_duplicates_block(monkeypatch):
    log, _, _, m = setup(monkeypatch)

    async def duplicates(name):
        return [m.row, {**m.row, "id": 13, "address": "영덕군 테스트길 10"}]

    m.search = duplicates
    result = await flow.graph.ainvoke({"information_version": "2", "message": "test"})
    assert result["status"] == "blocked" and [s[0] for s in log] == ["roster", "AS"]
    assert "마스터페이지 대상자 확인" in result["response"]
    assert "한 명" in result["response"]


@pytest.mark.asyncio
async def test_member_login_failure_reports_cause_and_retains_sheet_success(
    monkeypatch,
):
    log, _, _, m = setup(monkeypatch)

    async def denied():
        raise flow.MembersRejected("가입자 관리 요청이 거부되었습니다 (HTTP 401).")

    m.login = denied
    result = await flow.graph.ainvoke({"information_version": "2", "message": "test"})
    assert result["status"] == "blocked" and [s[0] for s in log] == ["roster", "AS"]
    assert (
        "마스터페이지 로그인" in result["response"] and "HTTP 401" in result["response"]
    )
    assert (
        result["receipts"]["roster"]["verified"]
        and result["receipts"]["as_update"]["verified"]
    )


@pytest.mark.asyncio
async def test_member_address_drift_before_save_still_blocks(monkeypatch):
    log, _, _, m = setup(monkeypatch)
    m.row["address"] = "영덕군 테스트길 10"

    async def changed(member_id):
        return {**m.row, "address": "다른길 10"}

    m.detail = changed
    result = await flow.graph.ainvoke({"information_version": "2", "message": "test"})
    assert result["status"] == "blocked" and [s[0] for s in log] == ["roster", "AS"]
    assert "가입자 재확인" in result["response"] and "변경" in result["response"]


def test_conflicting_member_address_reports_candidate_without_phone_override():
    selected = {
        "name": "김하늘",
        "address": "축산면 테스트길 8-2",
        "phone": "010-0000-1111",
    }
    candidate = {
        "id": 12,
        "full_name": "김하늘",
        "address": "서울 강남구 다른길 15-5",
        "mobile": "010-0000-1111",
    }
    with pytest.raises(ValueError) as caught:
        flow.resolve_information_member([candidate], selected, "영덕")
    assert "ID 12" in str(caught.value)
    assert selected["address"] in str(caught.value) and candidate["address"] in str(
        caught.value
    )
    assert "기록하지 않습니다" in str(caught.value)


@pytest.mark.parametrize(
    "candidates,expected",
    [
        ([], "동일 성함의 가입자를 찾지 못했습니다"),
        (
            [
                {"id": 12, "full_name": "김하늘", "address": "다른길 1"},
                {"id": 13, "full_name": "김하늘", "address": "다른길 2"},
            ],
            "2명 중 명부 주소",
        ),
    ],
)
def test_missing_and_unmatched_member_candidates_are_distinct(candidates, expected):
    with pytest.raises(ValueError, match=expected):
        flow.resolve_information_member(candidates, person(), "영덕")


@pytest.mark.asyncio
async def test_address_conflict_does_not_rewrite_notes_or_erase_sheet_success(
    monkeypatch,
):
    log, _, _, m = setup(monkeypatch)
    m.row["address"] = "서울 강남구 다른길 15-5"
    m.row["mobile"] = "010-0000-2222"
    original = m.row["general_notes"]
    result = await flow.graph.ainvoke({"information_version": "2", "message": "test"})
    assert (
        result["status"] == "blocked" and "주소가 명부와 다릅니다" in result["response"]
    )
    assert m.row["general_notes"] == original
    assert (
        result["receipts"]["roster"]["verified"]
        and result["receipts"]["as_update"]["verified"]
    )
    assert [s[0] for s in log] == ["roster", "AS"]

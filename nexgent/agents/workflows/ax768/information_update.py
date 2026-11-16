"""Information update: one roster identity, all matching AS cases, member history."""

import asyncio
import re
import unicodedata
from datetime import date
from typing import Literal, TypedDict

import httpx
from ax_integrations.ansimk_members import (
    AnsimkMembersClient,
    MembersError,
    MembersRejected,
)
from ax_integrations.chat import ModelRequestError
from ax_integrations.google_sheets import GoogleSheetsClient, SheetsError
from langgraph.graph import END, START, StateGraph

from workflows.ax768.as_update import korea_today
from workflows.ax768.city_search import USER_SHEETS
from workflows.ax768.graph import person_sheets_client
from workflows.ax768.information_policy import InformationPlan, note_for, prepare_plan
from workflows.ax768.information_sheets import (
    AS_LAYOUT,
    LAYOUTS,
    Table,
    describe_changes,
    matching_roster_rows,
    resolve_roster,
    roster_changes,
    same_name,
    select_as,
)
from workflows.ax768.member_note import compact, identity, notes_of

STAGES = ("roster", "as_update", "member_note")


class Input(TypedDict):
    information_version: Literal["2"]
    message: str


class State(Input, total=False):
    region: Literal["울진", "영덕", "광명"] | None
    status: str
    response: str
    plan: dict
    context: dict
    receipts: dict


def receipt(
    status="skipped",
    reason="앞 단계가 완료되지 않았습니다.",
    rows=None,
    changes=None,
    verified=False,
):
    return {
        "status": status,
        "reason": reason,
        "rows": rows or [],
        "changes": changes or [],
        "verified": verified,
    }


def stopped(state, stage, reason, dispatched=False):
    receipts = dict(state["receipts"])
    receipts[stage] = {
        **receipts[stage],
        "status": "unknown" if dispatched else "blocked",
        "reason": reason,
        "verified": False,
    }
    if dispatched:
        receipts[stage]["reason"] += (
            " 저장되었을 수 있으므로 재실행 전에 해당 기록을 확인해 주세요."
        )
    return {
        "status": "failed" if dispatched else "blocked",
        "response": receipts[stage]["reason"],
        "region": state.get("region"),
        "receipts": receipts,
    }


def tables(http, region):
    as_client = person_sheets_client(http)
    target = next(s for s in USER_SHEETS if s.city.startswith(region))
    roster = Table(
        GoogleSheetsClient(
            target.spreadsheet_id, as_client.token_provider, client=http
        ),
        target.sheet_id,
        target.start_row,
        LAYOUTS[region],
    )
    cases = Table(
        as_client, as_client.search_sheet_id, as_client.search_start_row, AS_LAYOUT
    )
    return roster, cases


def stage_failure_reason(error, phase):
    if isinstance(error, TimeoutError):
        detail = "처리 시간이 초과되었습니다."
    elif isinstance(error, (SheetsError, MembersError)) or type(error) is ValueError:
        # Adapter errors are locally defined, not raw response bodies.
        detail = str(error)[:500]
        detail = detail.replace(
            "Google response exceeded the data limit; narrow the range",
            "시트 조회 응답이 허용 크기를 초과했습니다.",
        )
    else:
        # ValidationError/KeyError/TypeError may include raw input or records.
        detail = "입력 또는 시트 응답 형식을 확인하지 못했습니다."
    return f"{phase}: {detail}"


async def find_roster(http, plan):
    """Visit approved rosters sequentially; never treat an error/ambiguity as absence."""
    for region in ("울진", "광명", "영덕"):
        roster, cases = tables(http, region)
        try:
            await roster.initialize()
            rows = await roster.find(plan.name)
        except SheetsError as exc:
            raise SheetsError(stage_failure_reason(exc, f"{region} 명부")) from None
        if not matching_roster_rows(plan, rows):
            continue
        try:
            await cases.initialize()
            as_rows = await cases.find(plan.name, information_only=True)
        except SheetsError as exc:
            raise SheetsError(stage_failure_reason(exc, "AS 시트")) from None
        selected = resolve_roster(plan, rows, as_rows)
        return region, roster, cases, selected, as_rows
    raise ValueError("세 지역 가입자 명부에서 일치하는 대상자를 찾지 못했습니다.")


async def plan_step(state):
    base = {
        "status": "running",
        "response": "",
        "receipts": {s: receipt() for s in STAGES},
        "context": {},
        "region": None,
    }
    try:
        if state.get("information_version") != "2":
            raise ValueError("정보확인 워크플로 버전을 확인해 주세요.")
        async with asyncio.timeout(95):
            plan = await prepare_plan(state.get("message", ""))
        return {**base, "plan": plan.model_dump()}
    except (ValueError, ModelRequestError, TimeoutError):
        return {
            **base,
            "status": "blocked",
            "response": "수정 요청을 확인하지 못했습니다. 한 가입자의 이름·기존 주소/번호와 수정할 정보를 구분해 입력해 주세요.",
        }


async def roster_step(state):
    dispatched = False
    phase = "가입자 조회"
    try:
        plan = InformationPlan.model_validate(state["plan"])
        async with (
            asyncio.timeout(240),
            httpx.AsyncClient(timeout=25, follow_redirects=False) as http,
        ):
            region, roster, cases, selected, as_rows = await find_roster(http, plan)
            state = {**state, "region": region}
            phase = "AS 대상 확인"
            matches = select_as(as_rows, selected)
            if len(matches) > 100:
                raise ValueError("동일 가입자의 AS가 100행을 초과해 중단했습니다.")
            layout, row = roster.layout, selected["row"]
            cols = [layout.name, layout.address, layout.phone, layout.birthday] + [
                c for slot in layout.guardians for c in slot
            ]
            phase = "가입자 행 재확인"
            before = await roster.snapshot(row, cols)
            if any(
                str(before[f"{c}{row}"]) != selected[k]
                for c, k in (
                    (layout.name, "name"),
                    (layout.address, "address"),
                    (layout.phone, "phone"),
                )
            ):
                raise ValueError("검색 후 가입자 행이 변경되었습니다.")
            phase = "수정 정보 확인"
            changes = roster_changes(plan, layout, row, before)
            snapshots = {}
            phase = "AS 행 재확인"
            for match in matches:
                n = match["row"]
                snapshot = await cases.snapshot(
                    n, ["C", "E", "H", "I", "K", "S", "X", "Y"]
                )
                if snapshot[f"C{n}"] != "정보확인" or any(
                    str(snapshot[f"{c}{n}"]) != match[k]
                    for c, k in (("H", "address"), ("I", "name"), ("K", "phone"))
                ):
                    raise ValueError("검색 후 AS 대상 행이 변경되었습니다.")
                snapshots.update(snapshot)
            today = korea_today().isoformat()
            note = note_for(plan, today)
            if len(note) > 500:
                raise ValueError(
                    "마스터페이지에 기록할 내용은 500자 이내로 입력해 주세요."
                )
            phase = "가입자 명부 저장 전 확인"
            await roster.check_headers()
            if await roster.cells(list(before), "FORMULA") != before:
                raise ValueError("저장 직전에 가입자 정보가 변경되었습니다.")
            state = {
                **state,
                "receipts": {
                    **state["receipts"],
                    "roster": receipt(
                        rows=[row], changes=describe_changes(layout, changes)
                    ),
                },
            }
            if changes:
                phase = "가입자 명부 저장 확인"
                dispatched = True
                await roster.write(before, changes)
            expected = dict(before)
            expected.update({f"{c}{r}": v for r, c, v, _ in changes})
            return {
                "region": region,
                "receipts": {
                    **state["receipts"],
                    "roster": receipt(
                        "updated",
                        "가입자 명부 저장 확인 완료."
                        if changes
                        else "이미 동일한 정보입니다.",
                        [row],
                        describe_changes(layout, changes),
                        True,
                    ),
                },
                "context": {
                    "selected": selected,
                    "as_rows": [m["row"] for m in matches],
                    "as_before": snapshots,
                    "roster_after": expected,
                    "today": today,
                    "note": note,
                },
            }
    except (SheetsError, ValueError, KeyError, TypeError, TimeoutError) as exc:
        return stopped(state, "roster", stage_failure_reason(exc, phase), dispatched)


async def as_step(state):
    dispatched = False
    ctx = state["context"]
    rows, before = ctx["as_rows"], ctx["as_before"]
    try:
        async with (
            asyncio.timeout(70),
            httpx.AsyncClient(timeout=25, follow_redirects=False) as http,
        ):
            roster, cases = tables(http, state["region"])
            await asyncio.gather(roster.initialize(), cases.initialize())
            if (
                await roster.cells(list(ctx["roster_after"]), "FORMULA")
                != ctx["roster_after"]
            ):
                raise ValueError("AS 처리 전에 명부가 변경되었습니다.")
            # Recheck the complete matching set, including confirmed absence.
            matches = select_as(
                await cases.find(ctx["selected"]["name"], information_only=True),
                ctx["selected"],
            )
            if [m["row"] for m in matches] != rows:
                raise ValueError("AS 대상 행 목록이 변경되었습니다.")
            if not rows:
                return {
                    "receipts": {
                        **state["receipts"],
                        "as_update": receipt(
                            "skipped",
                            "해당 가입자의 정보확인 AS가 없어 건너뛰었습니다.",
                            verified=True,
                        ),
                    }
                }
            if await cases.cells(list(before), "FORMULA") != before:
                raise ValueError("저장 직전에 AS 정보가 변경되었습니다.")
            serial = (date.fromisoformat(ctx["today"]) - date(1899, 12, 30)).days
            changes = [
                (r, c, v, d)
                for r in rows
                for c, v, d in [
                    ("Y", "정보확인완료", False),
                    ("X", serial, True),
                    ("S", "처리완료", False),
                ]
                if before.get(f"{c}{r}") != v
            ]
            state = {
                **state,
                "receipts": {
                    **state["receipts"],
                    "as_update": receipt(
                        rows=rows,
                        changes=[
                            "처리결과: 정보확인완료",
                            f"처리완료일: {ctx['today']}",
                            "진행상태: 처리완료",
                        ],
                    ),
                },
            }
            if changes:
                dispatched = True
                await cases.write(before, changes)
            return {
                "receipts": {
                    **state["receipts"],
                    "as_update": receipt(
                        "updated",
                        "일치하는 정보확인 AS 행을 모두 처리했습니다.",
                        rows,
                        [
                            "처리결과: 정보확인완료",
                            f"처리완료일: {ctx['today']}",
                            "진행상태: 처리완료",
                        ],
                        True,
                    ),
                }
            }
    except (SheetsError, ValueError, KeyError, TypeError, TimeoutError):
        return stopped(
            state,
            "as_update",
            "명부 반영 후 AS 처리 결과를 확인하지 못했습니다. AS 행을 확인해 주세요.",
            dispatched,
        )


def member_address_matches(roster_address, member_address, region):
    """Allow only known administrative prefixes of the resolved roster region."""
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
        return compact(value)

    return bool(canonical(roster_address)) and canonical(roster_address) == canonical(
        member_address
    )


def resolve_information_member(rows, selected, region):
    named = [r for r in rows if same_name(r.get("full_name", ""), selected["name"])]
    matches = [
        identity(r)
        for r in named
        if member_address_matches(selected["address"], r.get("address") or "", region)
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(
            f"이름·주소가 일치하는 가입자가 {len(matches)}명이라 한 명으로 확인하지 못했습니다."
        )
    if not named:
        raise ValueError("마스터페이지에서 동일 성함의 가입자를 찾지 못했습니다.")
    if len(named) == 1:
        candidate = identity(named[0])

        def label(value):
            return re.sub(r"\s+", " ", value).strip()[:140] or "주소 없음"

        raise ValueError(
            f"동일 성함 가입자(ID {candidate['member_id']})의 주소가 명부와 다릅니다. "
            f"명부: {label(selected['address'])} / 마스터: {label(candidate['address'])}. "
            "대상자 연결을 확인하기 전에는 일반사항을 기록하지 않습니다."
        )
    raise ValueError(
        f"동일 성함 가입자 {len(named)}명 중 명부 주소와 일치하는 가입자가 없습니다."
    )


async def member_step(state):
    dispatched = False
    phase = "마스터페이지 로그인"
    ctx = state["context"]
    try:
        async with (
            asyncio.timeout(120),
            httpx.AsyncClient(timeout=20, follow_redirects=False) as http,
        ):
            client = AnsimkMembersClient.from_env(http)
            await client.login()
            phase = "마스터페이지 대상자 확인"
            selected = ctx["selected"]
            if not selected["address"].strip():
                raise ValueError("마스터페이지 대상자 주소가 없습니다.")
            member = resolve_information_member(
                await client.search(selected["name"]), selected, state.get("region")
            )
            phase = "마스터페이지 가입자 재확인"
            before = await client.detail(member["member_id"])
            if identity(before) != member:
                raise ValueError("가입자 정보가 변경되었습니다.")
            phase = "기존 일반사항 확인"
            old = notes_of(before)
            desired = (
                old
                if ctx["note"] in old.splitlines()
                else old.rstrip() + ("\n" if old.strip() else "") + ctx["note"]
            )
            if len(desired) > 2000:
                raise ValueError(
                    "기존 일반사항을 보존하면 2,000자를 초과합니다. 기록을 정리한 후 다시 확인해 주세요."
                )
            state = {
                **state,
                "receipts": {
                    **state["receipts"],
                    "member_note": receipt(
                        rows=[member["member_id"]], changes=[ctx["note"]]
                    ),
                },
            }
            if desired != old:
                phase = "일반사항 저장 전 확인"
                fresh = await client.detail(member["member_id"])
                if identity(fresh) != member or notes_of(fresh) != old:
                    raise ValueError("저장 직전에 일반사항이 변경되었습니다.")
                phase = "일반사항 저장"
                dispatched = True
                try:
                    await client.write_notes(member["member_id"], desired)
                except MembersRejected:
                    dispatched = False
                    raise
                phase = "일반사항 저장 결과 확인"
                after = await client.detail(member["member_id"])
                if identity(after) != member or notes_of(after) != desired:
                    raise MembersError("저장 결과가 일치하지 않습니다.")
            return {
                "receipts": {
                    **state["receipts"],
                    "member_note": receipt(
                        "updated",
                        "기존 기록을 보존하고 일반사항을 기재했습니다.",
                        [member["member_id"]],
                        [ctx["note"]],
                        True,
                    ),
                },
                "status": "completed",
                "response": "가입자 명부, AS 처리와 마스터페이지 기록을 완료했습니다.",
            }
    except (MembersError, ValueError, KeyError, TypeError, TimeoutError) as exc:
        return stopped(
            state, "member_note", stage_failure_reason(exc, phase), dispatched
        )


def next_stage(next_name):
    return lambda state: next_name if state.get("status") == "running" else END


builder = StateGraph(State, input_schema=Input)
builder.add_node("prepare", plan_step)
builder.add_node("roster", roster_step)
builder.add_node("as_update", as_step)
builder.add_node("member_note", member_step)
builder.add_edge(START, "prepare")
builder.add_conditional_edges("prepare", next_stage("roster"))
builder.add_conditional_edges("roster", next_stage("as_update"))
builder.add_conditional_edges("as_update", next_stage("member_note"))
builder.add_edge("member_note", END)
graph = builder.compile()

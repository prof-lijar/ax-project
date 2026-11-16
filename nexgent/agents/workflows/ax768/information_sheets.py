"""Pinned, header-checked information-update cells; no model-selected ranges."""

import asyncio
from dataclasses import dataclass

from ax_integrations.google_sheets import SheetsError
from ax_integrations.sheets_address import address_pattern, normalize_address
from ax_integrations.sheets_lookup import normalize_person_name

from .as_update import cell_update
from .information_policy import phone, valid_phone


@dataclass(frozen=True)
class Layout:
    name: str
    address: str
    phone: str
    birthday: str
    guardians: tuple[tuple[str, str, str], ...]
    headers: dict[str, str]


# Checked read-only against all three live roster headers on 2026-11-12.
LAYOUTS = {
    "울진": Layout(
        "C",
        "H",
        "O",
        "E",
        (("R", "S", "T"), ("U", "V", "W")),
        {
            "C3": "성명",
            "H3": "도로명 주소",
            "O3": "휴대전화",
            "E3": "생년월일",
            "R3": "보호자1",
            "U3": "보호자2",
            "R4": "성명",
            "S4": "연락처",
            "T4": "관계",
            "U4": "성명",
            "V4": "연락처",
            "W4": "관계",
        },
    ),
    "영덕": Layout(
        "C",
        "H",
        "O",
        "E",
        (("Q", "R", "S"), ("T", "U", "V")),
        {
            "C3": "성명",
            "H3": "도로명 주소",
            "O3": "휴대전화",
            "E3": "생년월일",
            "Q3": "보호자1",
            "T3": "보호자2",
            "Q4": "성명",
            "R4": "연락처",
            "S4": "관계",
            "T4": "성명",
            "U4": "연락처",
            "V4": "관계",
        },
    ),
    "광명": Layout(
        "D",
        "G",
        "H",
        "E",
        (("J", "K", "L"), ("M", "N", "O"), ("P", "Q", "R"), ("S", "T", "U")),
        {
            "D3": "성명",
            "G3": "설치주소",
            "H4": "휴대전화",
            "E3": "생년월일",
            **{
                f"{col}4": f"보호자{i} {label}"
                for i, cols in enumerate(
                    (
                        ("J", "K", "L"),
                        ("M", "N", "O"),
                        ("P", "Q", "R"),
                        ("S", "T", "U"),
                    ),
                    1,
                )
                for col, label in zip(cols, ("성명", "연락처", "관계"))
            },
        },
    ),
}
AS_LAYOUT = Layout(
    "I",
    "H",
    "K",
    "",
    (),
    {
        "C6": "AS구분",
        "E6": "지역",
        "H6": "주소",
        "I6": "가입자",
        "K6": "전화번호",
        "S6": "진행상태",
        "X6": "처리완료일",
        "Y6": "처리결과",
    },
)


def same_name(a, b):
    return normalize_person_name(a).removesuffix("님") == normalize_person_name(
        b
    ).removesuffix("님")


def matches_address(query, value):
    return bool(address_pattern(query).search(normalize_address(value)))


def col_index(col):
    result = 0
    for char in col:
        result = result * 26 + ord(char) - 64
    return result - 1


async def gather_reads(*operations):
    """Drain sibling reads before their HTTP client closes on failure/cancellation."""
    tasks = [asyncio.create_task(operation) for operation in operations]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


class Table:
    def __init__(self, client, gid, start, layout):
        self.client, self.gid, self.start, self.layout = client, gid, start, layout
        self.title = ""
        self.end = 0

    async def initialize(self):
        metadata = await self.client.metadata()
        tab = next(
            (
                s["properties"]
                for s in metadata.get("sheets", [])
                if s["properties"]["sheetId"] == self.gid
            ),
            None,
        )
        if not tab or not self.start <= tab["gridProperties"]["rowCount"] <= 20000:
            raise SheetsError("명부 또는 AS시트의 범위를 확인해 주세요.")
        self.title = "'" + tab["title"].replace("'", "''") + "'"
        self.end = tab["gridProperties"]["rowCount"]
        await self.check_headers()

    async def read(self, ranges, render="FORMATTED_VALUE"):
        value = await self.client._request(
            "GET",
            "/values:batchGet",
            params={
                "ranges": [f"{self.title}!{r}" for r in ranges],
                "valueRenderOption": render,
                "dateTimeRenderOption": "SERIAL_NUMBER",
            },
        )
        batches = value.get("valueRanges")
        if not isinstance(batches, list) or len(batches) != len(ranges):
            raise SheetsError("시트 읽기 결과가 누락되어 중단했습니다.")
        return [v.get("values", []) for v in batches]

    async def cells(self, addresses, render="FORMATTED_VALUE"):
        return {
            a: (v[0][0] if v and v[0] else "")
            for a, v in zip(addresses, await self.read(addresses, render))
        }

    async def check_headers(self):
        values = await self.cells(list(self.layout.headers))
        if any(
            normalize_person_name(values[a]) != normalize_person_name(v)
            for a, v in self.layout.headers.items()
        ):
            raise SheetsError("시트 컬럼 구성이 변경되어 중단했습니다.")

    async def find(self, name, information_only=False):
        # Scan only names. Addresses/phones for 1,000 rows can exceed the shared
        # 128 KB transport limit, even when the requested person is absent.
        semaphore = asyncio.Semaphore(3)

        async def scan(start):
            end = min(start + 999, self.end)
            column = self.layout.name
            async with semaphore:
                (values,) = await self.read([f"{column}{start}:{column}{end}"])
            return [
                start + offset
                for offset, cells in enumerate(values)
                if cells and same_name(str(cells[0]), name)
            ]

        matches = [
            row
            for batch in await gather_reads(
                *(scan(start) for start in range(self.start, self.end + 1, 1000))
            )
            for row in batch
        ]
        columns = [self.layout.name, self.layout.address, self.layout.phone]
        if information_only:
            columns.append("C")

        async def details(rows):
            addresses = [f"{col}{row}" for row in rows for col in columns]
            async with semaphore:
                values = await self.cells(addresses)
            result = []
            for row in rows:
                actual_name = str(values[f"{self.layout.name}{row}"])
                if not same_name(actual_name, name):
                    raise SheetsError("검색 중 가입자 이름이 변경되어 중단했습니다.")
                if information_only and str(values[f"C{row}"]).strip() != "정보확인":
                    continue
                result.append(
                    {
                        "row": row,
                        "name": actual_name,
                        "address": str(values[f"{self.layout.address}{row}"]),
                        "phone": str(values[f"{self.layout.phone}{row}"]),
                    }
                )
            return result

        # Keep matching-row detail responses bounded too; preserve sheet order.
        return [
            row
            for batch in await gather_reads(
                *(
                    details(matches[start : start + 20])
                    for start in range(0, len(matches), 20)
                )
            )
            for row in batch
        ]

    async def snapshot(self, row, cols):
        return await self.cells([f"{c}{row}" for c in dict.fromkeys(cols)], "FORMULA")

    async def write(self, before, changes):
        # Caller marks dispatch BEFORE this method. Any error here is conservatively unknown.
        requests = [
            cell_update(self.gid, row, col_index(col), value, date_cell=is_date)
            for row, col, value, is_date in changes
        ]
        await self.client._request("POST", ":batchUpdate", json={"requests": requests})
        expected = dict(before)
        expected.update({f"{col}{row}": value for row, col, value, _ in changes})
        checked = await self.cells(list(expected), "FORMULA")
        if checked != expected:
            raise SheetsError("저장 후 시트 값 또는 대상자 정보가 일치하지 않습니다.")


def matching_roster_rows(plan, rows):
    return [
        r
        for r in rows
        if (not plan.address or matches_address(plan.address, r["address"]))
        and (not plan.current_phone or phone(plan.current_phone) == phone(r["phone"]))
    ]


def resolve_roster(plan, rows, as_rows):
    candidates = matching_roster_rows(plan, rows)
    # A unique same-name record is sufficient; otherwise use information-confirmation AS evidence.
    if len(candidates) != 1:
        evidence = [
            a
            for a in as_rows
            if (not plan.address or matches_address(plan.address, a["address"]))
            and (
                not plan.current_phone or phone(plan.current_phone) == phone(a["phone"])
            )
        ]
        candidates = [
            r
            for r in candidates
            if any(
                (valid_phone(a["phone"]) and phone(a["phone"]) == phone(r["phone"]))
                or (
                    a["address"].strip()
                    and normalize_address(a["address"])
                    == normalize_address(r["address"])
                )
                for a in evidence
            )
        ]
    if len(candidates) != 1:
        raise ValueError(
            "가입자 명부에서 한 행을 특정하지 못했습니다. 주소·기존 가입자 번호를 확인해 주세요."
        )
    return candidates[0]


def select_as(rows, roster):
    if not rows:
        return []
    if len(rows) == 1 and (
        normalize_address(rows[0]["address"]) == normalize_address(roster["address"])
        and roster["address"].strip()
    ):
        # Conflicting existing phone is not silently ignored.
        if rows[0]["phone"].strip() and phone(rows[0]["phone"]) != phone(
            roster["phone"]
        ):
            raise ValueError(
                "AS시트와 명부의 가입자 번호가 다릅니다. 기존 번호를 확인해 주세요."
            )
        return rows
    if not valid_phone(roster["phone"]):
        raise ValueError("동명이인 AS 확인에 필요한 기존 가입자 번호가 없습니다.")
    selected = [r for r in rows if phone(r["phone"]) == phone(roster["phone"])]
    if not selected:
        if all(
            valid_phone(r["phone"])
            and normalize_address(r["address"]) != normalize_address(roster["address"])
            for r in rows
        ):
            return []  # Same-name cases belong to other subscribers.
        raise ValueError("동일 성함의 AS가 있으나 가입자 번호가 일치하지 않습니다.")
    return selected


def roster_changes(plan, layout, row, before):
    changes = []

    def add(col, value):
        old = before[f"{col}{row}"]
        if isinstance(old, str) and old.startswith("="):
            raise ValueError("수정 대상 셀에 수식이 있어 중단했습니다.")
        if old != value:
            changes.append((row, col, value, False))

    if plan.birthday:
        add(layout.birthday, plan.birthday)
    if plan.new_phone:
        add(layout.phone, plan.new_phone)
    if plan.guardian:
        g = plan.guardian
        slots = [
            (cols, [str(before[f"{c}{row}"]) for c in cols])
            for cols in layout.guardians
        ]
        if g.mode == "add":
            existing = [
                (cols, vals) for cols, vals in slots if phone(vals[1]) == phone(g.phone)
            ]
            if existing:
                if (
                    len(existing) != 1
                    or (g.name and existing[0][1][0] != g.name)
                    or (g.relationship and existing[0][1][2] != g.relationship)
                ):
                    raise ValueError(
                        "동일 보호자 번호의 성명·관계가 다릅니다. 기존 보호자를 확인해 주세요."
                    )
                return changes
            choices = [cols for cols, vals in slots if not any(v.strip() for v in vals)]
            if not choices:
                raise ValueError(
                    "빈 보호자 칸이 없습니다. 기존 보호자를 덮어쓰지 않았습니다."
                )
            cols = choices[0]
        else:
            choices = [
                cols for cols, vals in slots if phone(vals[1]) == phone(g.current_phone)
            ]
            if len(choices) != 1:
                raise ValueError("교체할 보호자 번호가 한 칸으로 확인되지 않습니다.")
            cols = choices[0]
        for col, value in zip(cols, (g.name, g.phone, g.relationship)):
            if value:
                add(col, value)
    return changes


def describe_changes(layout, changes):
    labels = {layout.birthday: "생년월일", layout.phone: "가입자 전화번호"}
    for index, cols in enumerate(layout.guardians, 1):
        labels.update(
            {
                c: f"보호자 {index} {name}"
                for c, name in zip(cols, ("성명", "연락처", "관계"))
            }
        )
    return [f"{labels[c]}: {value}" for _, c, value, _ in changes]

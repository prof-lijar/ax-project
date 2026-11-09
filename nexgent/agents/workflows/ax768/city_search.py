"""Ordered, read-only lookup across the three operator-approved user rosters."""

from dataclasses import dataclass

from ax_integrations.google_sheets import GoogleSheetsClient, SheetsError
from ax_integrations.sheets_person import search_person


@dataclass(frozen=True)
class UserSheet:
    alias: str
    city: str
    spreadsheet_id: str
    sheet_id: int
    name_column: str
    address_column: str
    start_row: int


USER_SHEETS = (
    UserSheet(
        "uljin-users",
        "울진군",
        "1Md868AWFklkeLfvgkbc8AAHmxiPmxf5EkFxp-dZJ7uU",
        177570717,
        "C",
        "H",
        6,
    ),
    UserSheet(
        "gwangmyeon-users",
        "광명시",
        "1YJpn3nPyrRdBTgHrejVq8NSzo4-EMiYz-wBJI-Hyuhs",
        1895743441,
        "D",
        "G",
        5,
    ),
    UserSheet(
        "yeongdeok-users",
        "영덕군",
        "1v70ievxZha1xeq0N6jse_7MSmF6RuPEuyXRrFV6ZA1E",
        2024273886,
        "C",
        "H",
        6,
    ),
)


async def search_user_sheets(http, token_provider, action):
    attempts = []
    base = {
        "name": action.name,
        "query": action.address,
        "attempts": attempts,
        "city": None,
        "sheet_alias": None,
        "selected_row": None,
    }
    for target in USER_SHEETS:
        client = GoogleSheetsClient(target.spreadsheet_id, token_provider, client=http)
        try:
            result = await search_person(
                client,
                sheet_id=target.sheet_id,
                name=action.name,
                address=action.address,
                name_column=target.name_column,
                address_column=target.address_column,
                start_row=target.start_row,
            )
        except (SheetsError, ValueError) as exc:
            attempts.append(
                {
                    "sheet_alias": target.alias,
                    "city": target.city,
                    "status": "failed",
                    "error": str(exc),
                }
            )
            return {**base, "status": "failed", "error": f"{target.alias}: {exc}"}
        attempts.append(
            {
                "sheet_alias": target.alias,
                "city": target.city,
                "status": result["status"],
            }
        )
        if result["status"] == "found":
            return {
                **base,
                **result,
                "city": target.city,
                "sheet_alias": target.alias,
                "spreadsheet_id": target.spreadsheet_id,
                "sheet_url": f"https://docs.google.com/spreadsheets/d/{target.spreadsheet_id}/edit#gid={target.sheet_id}&range=A{result['selected_row']}",
            }
    return {**base, "status": "not_found"}


def result_message(result):
    query = f"{result['name']} / {result['query']}"
    if result["status"] == "failed":
        return (
            f"'{query}' 조회 중 오류가 발생하여 검색을 중단했습니다. {result['error']}"
        )
    if result["status"] == "not_found":
        return f"'{query}' 이름과 주소가 같은 행을 울진군 → 광명시 → 영덕군 명부에서 찾지 못했습니다."
    return (
        f"'{query}' 일치: {result['city']} 사용자 ({result['sheet_alias']}). "
        f"'{result['sheet_title']}' 최신 일치 행: {result['selected_row']}행.\n"
        f"{result['sheet_url']}"
    )

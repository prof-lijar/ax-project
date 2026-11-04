"""Bounded exact-cell search and verified background-only formatting."""

import unicodedata
from urllib.parse import quote

from ax_integrations.google_sheets import SheetsError

MAX_SEARCH_CELLS = 100_000
PAGE_CELLS = 2000
MAX_MATCHES = 100


def normalize_name(value):
    return unicodedata.normalize("NFC", str(value)).strip()


def first_value(value_range):
    rows = value_range.get("values") or []
    return rows[0][0] if rows and rows[0] else ""


def column_label(index):
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def yellow(color):
    rgb = color.get("backgroundColorStyle", {}).get(
        "rgbColor", color.get("backgroundColor", {})
    )
    return (
        rgb.get("red", 0) == 1 and rgb.get("green", 0) == 1 and rgb.get("blue", 0) == 0
    )


async def find_and_highlight(client, *, sheet_id: int, name: str):
    name = normalize_name(name)
    if not name:
        raise ValueError("name must not be blank")
    metadata = await client.metadata()
    tab = next(
        (
            s["properties"]
            for s in metadata.get("sheets", [])
            if s["properties"]["sheetId"] == sheet_id
        ),
        None,
    )
    if tab is None:
        raise SheetsError("Configured name-search tab was not found")
    grid = tab.get("gridProperties", {})
    rows, columns = grid.get("rowCount", 0), grid.get("columnCount", 0)
    if (
        not rows
        or not columns
        or columns > PAGE_CELLS
        or rows * columns > MAX_SEARCH_CELLS
    ):
        raise SheetsError(
            "Name-search grid exceeds the 100,000-cell limit; no highlight applied"
        )
    title = "'" + tab["title"].replace("'", "''") + "'"
    page_rows = max(1, PAGE_CELLS // columns)
    matches = []
    for start in range(0, rows, page_rows):
        end = min(start + page_rows, rows)
        span = f"{title}!A{start + 1}:{column_label(columns)}{end}"
        page = await client._request(
            "GET",
            "/values/" + quote(span, safe=""),
            params={"valueRenderOption": "FORMATTED_VALUE"},
        )
        for row_offset, row in enumerate(page.get("values", [])):
            for column, value in enumerate(row):
                if normalize_name(value) == name:
                    matches.append((start + row_offset, column))
                    if len(matches) > MAX_MATCHES:
                        raise SheetsError(
                            "More than 100 exact matches; no highlight applied"
                        )
    total_match_count = len(matches)
    # Latest is defined by the user as bottom-most, not a date-column value.
    # Resolve same-row ties left-to-right to change just one name cell.
    if matches:
        matches = [max(matches, key=lambda pos: (pos[0], -pos[1]))]
    ranges = [f"{title}!{column_label(c + 1)}{r + 1}" for r, c in matches]
    base = {
        "name": name,
        "sheet_id": sheet_id,
        "sheet_title": tab["title"],
        "matched_cells": ranges,
        "match_count": len(matches),
        "total_match_count": total_match_count,
        "selected_row": matches[0][0] + 1 if matches else None,
    }
    if not matches:
        return {**base, "status": "not_found", "verified": True}
    # Re-read exact targets before writing. A concurrent edit can still race the write.
    checks = await client._request(
        "GET",
        "/values:batchGet",
        params={
            "ranges": ranges,
            "valueRenderOption": "FORMATTED_VALUE",
        },
    )
    values = checks.get("valueRanges", [])
    if len(values) != len(matches) or any(
        normalize_name(first_value(v)) != name for v in values
    ):
        raise SheetsError("A matched name changed during search; no highlight applied")
    requests = [
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": r,
                    "endRowIndex": r + 1,
                    "startColumnIndex": c,
                    "endColumnIndex": c + 1,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColorStyle": {
                            "rgbColor": {"red": 1, "green": 1, "blue": 0},
                        }
                    }
                },
                "fields": "userEnteredFormat.backgroundColorStyle",
            }
        }
        for r, c in matches
    ]
    await client._request("POST", ":batchUpdate", json={"requests": requests})
    data = await client._request(
        "GET",
        params={
            "ranges": ranges,
            "fields": (
                "sheets(data(startRow,startColumn,rowData(values(formattedValue,"
                "userEnteredFormat(backgroundColor,backgroundColorStyle),"
                "effectiveFormat(backgroundColor,backgroundColorStyle)))))"
            ),
        },
    )
    verified = set()
    for sheet in data.get("sheets", []):
        for block in sheet.get("data", []):
            for dr, row in enumerate(block.get("rowData", [])):
                for dc, cell in enumerate(row.get("values", [])):
                    pos = (
                        block.get("startRow", 0) + dr,
                        block.get("startColumn", 0) + dc,
                    )
                    if (
                        normalize_name(cell.get("formattedValue", "")) == name
                        and yellow(cell.get("userEnteredFormat", {}))
                        and yellow(cell.get("effectiveFormat", {}))
                    ):
                        verified.add(pos)
    return {
        **base,
        "status": "highlighted" if set(matches) <= verified else "verification_failed",
        "verified": set(matches) <= verified,
    }

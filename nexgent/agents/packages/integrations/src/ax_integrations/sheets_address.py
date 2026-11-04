"""Bounded address search and verified bottom-most row highlighting."""

import re
import unicodedata
from urllib.parse import quote

from ax_integrations.google_sheets import SheetsError
from ax_integrations.sheets_highlight import column_label, first_value, yellow

MAX_SEARCH_CELLS = 100_000
PAGE_CELLS = 2000
MAX_MATCHES = 100


def normalize_address(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", str(value))).casefold()


def address_pattern(address):
    value = normalize_address(address)
    if not value:
        raise ValueError("address must not be blank")
    # Literal substring matching, but 158 must not match 1580 or 1158.
    prefix = r"(?<!\d)" if value[0].isdigit() else ""
    suffix = r"(?!\d)" if value[-1].isdigit() else ""
    return re.compile(prefix + re.escape(value) + suffix)


async def search_address(
    client, *, sheet_id: int, address: str, columns: str | None = None
):
    pattern = address_pattern(address)
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
        raise SheetsError("Configured address-search tab was not found")
    grid = tab.get("gridProperties", {})
    rows, grid_columns = grid.get("rowCount", 0), grid.get("columnCount", 0)
    first, last = 1, grid_columns
    if columns is not None:
        if not re.fullmatch(r"[A-Z]{1,3}:[A-Z]{1,3}", columns):
            raise ValueError("Address columns must be a span such as G:H")
        indices = []
        for label in columns.split(":"):
            index = 0
            for character in label:
                index = index * 26 + ord(character) - ord("A") + 1
            indices.append(index)
        first, last = indices
        if not 1 <= first <= last <= grid_columns:
            raise ValueError("Address columns are outside the configured tab")
    width = last - first + 1
    if (
        not rows
        or not grid_columns
        or width > PAGE_CELLS
        or rows * width > MAX_SEARCH_CELLS
    ):
        raise SheetsError(
            "Address-search range exceeds the 100,000-cell limit; configure narrower address columns"
        )
    title = "'" + tab["title"].replace("'", "''") + "'"
    matches = {}
    matched_cells = 0
    page_rows = max(1, PAGE_CELLS // width)
    for start in range(0, rows, page_rows):
        end = min(start + page_rows, rows)
        span = f"{title}!{column_label(first)}{start + 1}:{column_label(last)}{end}"
        data = await client._request(
            "GET",
            "/values/" + quote(span, safe=""),
            params={"valueRenderOption": "FORMATTED_VALUE"},
        )
        for dr, row in enumerate(data.get("values", [])):
            for column, value in enumerate(row):
                if isinstance(value, str) and pattern.search(normalize_address(value)):
                    row_number = start + dr + 1
                    matches.setdefault(row_number, []).append(
                        {
                            "cell": f"{title}!{column_label(column + first)}{row_number}",
                            "address": value[:1000],
                            "truncated": len(value) > 1000,
                        }
                    )
                    matched_cells += 1
                    if matched_cells > MAX_MATCHES:
                        raise SheetsError(
                            "More than 100 address matches; use a more specific address"
                        )
    ordered = [
        {"row": row, "cells": matches[row]} for row in sorted(matches, reverse=True)
    ]
    return {
        "status": "found" if ordered else "not_found",
        "query": address.strip(),
        "sheet_id": sheet_id,
        "sheet_title": tab["title"],
        "matches": ordered,
        "match_count": len(ordered),
        "selected_row": ordered[0]["row"] if ordered else None,
        "column_count": grid_columns,
    }


async def highlight_address_row(client, *, sheet_id: int, address: str, columns=None):
    result = await search_address(
        client, sheet_id=sheet_id, address=address, columns=columns
    )
    if not result["matches"]:
        return {**result, "verified": True, "highlighted_range": None}
    row = result["selected_row"]
    width = result["column_count"]
    if width > 2000:
        raise SheetsError(
            "Row highlight exceeds the 2000-cell limit; no highlight applied"
        )
    targets = [cell["cell"] for cell in result["matches"][0]["cells"]]
    checks = await client._request(
        "GET",
        "/values:batchGet",
        params={"ranges": targets, "valueRenderOption": "FORMATTED_VALUE"},
    )
    values = checks.get("valueRanges", [])
    pattern = address_pattern(address)
    if len(values) != len(targets) or any(
        not pattern.search(normalize_address(first_value(value))) for value in values
    ):
        raise SheetsError(
            "Selected address changed during search; no highlight applied"
        )
    formatting = await highlight_row_yellow(
        client, sheet_id=sheet_id, title=result["sheet_title"], row=row, width=width
    )
    return {**result, **formatting}


async def highlight_row_yellow(client, *, sheet_id, title, row, width):
    """Apply background-only row formatting and verify every existing column."""
    if not 1 <= width <= 2000 or row < 1:
        raise SheetsError("Invalid or oversized row highlight")
    title = "'" + title.replace("'", "''") + "'"
    span = f"{title}!A{row}:{column_label(width)}{row}"
    await client._request(
        "POST",
        ":batchUpdate",
        json={
            "requests": [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": row - 1,
                            "endRowIndex": row,
                            "startColumnIndex": 0,
                            "endColumnIndex": width,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColorStyle": {
                                    "rgbColor": {"red": 1, "green": 1, "blue": 0}
                                }
                            }
                        },
                        "fields": "userEnteredFormat.backgroundColorStyle",
                    }
                }
            ]
        },
    )
    data = await client._request(
        "GET",
        params={
            "ranges": [span],
            "fields": (
                "sheets(data(startRow,startColumn,rowData(values("
                "userEnteredFormat(backgroundColor,backgroundColorStyle),"
                "effectiveFormat(backgroundColor,backgroundColorStyle)))))"
            ),
        },
    )
    verified_columns = set()
    stored_columns = set()
    overridden_columns = set()
    for sheet in data.get("sheets", []):
        for block in sheet.get("data", []):
            for dr, item in enumerate(block.get("rowData", [])):
                if block.get("startRow", 0) + dr != row - 1:
                    continue
                for dc, cell in enumerate(item.get("values", [])):
                    if yellow(cell.get("userEnteredFormat", {})):
                        stored_columns.add(block.get("startColumn", 0) + dc)
                    if yellow(cell.get("userEnteredFormat", {})) and not yellow(
                        cell.get("effectiveFormat", {})
                    ):
                        overridden_columns.add(block.get("startColumn", 0) + dc)
                    if yellow(cell.get("userEnteredFormat", {})) and yellow(
                        cell.get("effectiveFormat", {})
                    ):
                        verified_columns.add(block.get("startColumn", 0) + dc)
    verified = set(range(width)) <= verified_columns
    stored_verified = set(range(width)) <= stored_columns
    return {
        "verified": verified,
        "stored_verified": stored_verified,
        "highlighted_range": span,
        "status": (
            "highlighted"
            if verified
            else "highlighted_with_warnings"
            if stored_verified
            else "verification_failed"
        ),
        "overridden_cells": [
            f"{title}!{column_label(column + 1)}{row}"
            for column in sorted(overridden_columns)[:20]
        ],
        "overridden_cell_count": len(overridden_columns),
    }

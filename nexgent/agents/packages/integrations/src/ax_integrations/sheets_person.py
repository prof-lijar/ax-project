"""Bottom-up same-row name/address matching with verified row highlighting."""

import re
from urllib.parse import quote

from ax_integrations.google_sheets import SheetsError
from ax_integrations.sheets_address import (
    address_pattern,
    highlight_row_yellow,
    normalize_address,
)
from ax_integrations.sheets_highlight import column_label, first_value, normalize_name

PAGE_CELLS = 2000
MAX_SEARCH_CELLS = 100_000


def column_index(label):
    if not isinstance(label, str) or not re.fullmatch(r"[A-Z]{1,3}", label):
        raise ValueError("Configure a single column letter for name and address")
    index = 0
    for character in label:
        index = index * 26 + ord(character) - ord("A") + 1
    return index


async def search_person(
    client, *, sheet_id, name, address, name_column, address_column, start_row=1
):
    name = normalize_name(name)
    if not name:
        raise ValueError("name must not be blank")
    pattern = address_pattern(address)
    nc, ac = column_index(name_column), column_index(address_column)
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
        raise SheetsError("Configured person-search tab was not found")
    grid = tab.get("gridProperties", {})
    rows, columns = grid.get("rowCount", 0), grid.get("columnCount", 0)
    first, last = min(nc, ac), max(nc, ac)
    width = last - first + 1
    if not (1 <= start_row <= rows and last <= columns <= 2000 and nc != ac):
        raise SheetsError("Invalid person-search row or column configuration")
    if (rows - start_row + 1) * width > MAX_SEARCH_CELLS:
        raise SheetsError("Person-search range exceeds the 100,000-cell limit")
    title = "'" + tab["title"].replace("'", "''") + "'"
    base = {
        "name": name,
        "query": address.strip(),
        "sheet_id": sheet_id,
        "sheet_title": tab["title"],
        "selected_row": None,
        "match_count": 0,
        "matches": [],
        "highlighted_range": None,
        "column_count": columns,
    }
    page_rows = max(1, PAGE_CELLS // width)
    end = rows
    while end >= start_row:
        start = max(start_row, end - page_rows + 1)
        span = f"{title}!{column_label(first)}{start}:{column_label(last)}{end}"
        data = await client._request(
            "GET",
            "/values/" + quote(span, safe=""),
            params={"valueRenderOption": "FORMATTED_VALUE"},
        )
        values = data.get("values", [])
        for offset in range(len(values) - 1, -1, -1):
            values_row = values[offset]

            def value_at(column, values_row=values_row):
                index = column - first
                return values_row[index] if index < len(values_row) else ""

            found_name, found_address = value_at(nc), value_at(ac)
            if normalize_name(found_name) != name or not pattern.search(
                normalize_address(found_address)
            ):
                continue
            row = start + offset
            name_cell, address_cell = (
                f"{title}!{name_column}{row}",
                f"{title}!{address_column}{row}",
            )
            checks = await client._request(
                "GET",
                "/values:batchGet",
                params={
                    "ranges": [name_cell, address_cell],
                    "valueRenderOption": "FORMATTED_VALUE",
                },
            )
            checked = checks.get("valueRanges", [])
            if (
                len(checked) != 2
                or normalize_name(first_value(checked[0])) != name
                or not pattern.search(normalize_address(first_value(checked[1])))
            ):
                raise SheetsError("Selected name/address changed; no highlight applied")
            return {
                **base,
                "status": "found",
                "verified": True,
                "selected_row": row,
                "match_count": 1,
                "name_cell": name_cell,
                "matches": [
                    {
                        "row": row,
                        "cells": [
                            {
                                "cell": address_cell,
                                "address": str(found_address)[:1000],
                                "truncated": len(str(found_address)) > 1000,
                            }
                        ],
                    }
                ],
            }
        end = start - 1
    return {**base, "status": "not_found", "verified": True}


async def find_and_highlight_person(
    client, *, sheet_id, name, address, name_column, address_column, start_row=1
):
    result = await search_person(
        client,
        sheet_id=sheet_id,
        name=name,
        address=address,
        name_column=name_column,
        address_column=address_column,
        start_row=start_row,
    )
    if result["status"] == "not_found":
        return result
    formatting = await highlight_row_yellow(
        client,
        sheet_id=sheet_id,
        title=result["sheet_title"],
        row=result["selected_row"],
        width=result["column_count"],
    )
    return {**result, **formatting}

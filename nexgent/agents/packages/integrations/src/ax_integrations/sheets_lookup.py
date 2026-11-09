"""Bounded, GET-only latest-row lookup with address-grounded name suggestions."""

import re
import unicodedata
from urllib.parse import quote

from ax_integrations.google_sheets import SheetsError
from ax_integrations.sheets_address import address_pattern, normalize_address
from ax_integrations.sheets_highlight import column_label, first_value
from ax_integrations.sheets_person import column_index

MAX_CELLS = 100_000
PAGE_CELLS = 2000
MAX_CANDIDATES = 10


def normalize_person_name(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value)))


def close_name(left, right):
    return (
        3 <= len(left) <= 5
        and len(left) == len(right)
        and re.fullmatch(r"[가-힣]+", left) is not None
        and re.fullmatch(r"[가-힣]+", right) is not None
        and sum(a != b for a, b in zip(left, right)) == 1
    )


async def lookup_person(
    client,
    *,
    sheet_id,
    name,
    address,
    name_column,
    address_column,
    start_row=1,
    suggest_names=False,
):
    name = normalize_person_name(name)
    pattern = address_pattern(address) if address else None
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
        raise SheetsError("Configured lookup tab was not found")
    grid = tab.get("gridProperties", {})
    rows, columns = grid.get("rowCount", 0), grid.get("columnCount", 0)
    first, last = min(nc, ac), max(nc, ac)
    width = last - first + 1
    if not (1 <= start_row <= rows and last <= columns and nc != ac):
        raise SheetsError("Invalid lookup row/column configuration")
    if width > PAGE_CELLS or (rows - start_row + 1) * width > MAX_CELLS:
        raise SheetsError("Lookup range exceeds the 100,000-cell limit")
    title = "'" + tab["title"].replace("'", "''") + "'"
    base = {
        "sheet_id": sheet_id,
        "sheet_title": tab["title"],
        "candidates": [],
        "candidates_truncated": False,
        "status": "not_found",
    }
    seen = set()
    end = rows
    while end >= start_row:
        start = max(start_row, end - max(1, PAGE_CELLS // width) + 1)
        span = f"{title}!{column_label(first)}{start}:{column_label(last)}{end}"
        data = await client._request(
            "GET",
            "/values/" + quote(span, safe=""),
            params={"valueRenderOption": "FORMATTED_VALUE"},
        )
        values = data.get("values", [])
        for offset in range(len(values) - 1, -1, -1):
            row_values = values[offset]
            actual_name = normalize_person_name(
                row_values[nc - first] if nc - first < len(row_values) else ""
            )
            actual_address = str(
                row_values[ac - first] if ac - first < len(row_values) else ""
            )
            if pattern and not pattern.search(normalize_address(actual_address)):
                continue
            exact = actual_name == name
            if not exact and not (
                suggest_names and pattern and close_name(name, actual_name)
            ):
                continue
            row = start + offset
            match = {"row": row, "name": actual_name, "address": actual_address[:1000]}
            if exact:
                checked = await client._request(
                    "GET",
                    "/values:batchGet",
                    params={
                        "ranges": [
                            f"{title}!{name_column}{row}",
                            f"{title}!{address_column}{row}",
                        ],
                        "valueRenderOption": "FORMATTED_VALUE",
                    },
                )
                cells = checked.get("valueRanges", [])
                if (
                    len(cells) != 2
                    or normalize_person_name(first_value(cells[0])) != name
                    or (
                        pattern
                        and not pattern.search(normalize_address(first_value(cells[1])))
                    )
                ):
                    raise SheetsError(
                        "Selected name/address changed during lookup; run the search again"
                    )
                return {
                    **base,
                    **match,
                    "address": str(first_value(cells[1]))[:1000],
                    "status": "found",
                    "candidates": [],
                    "candidates_truncated": False,
                }
            # Suggestions are evidence, never automatic matches. Latest row per distinct name.
            if actual_name not in seen:
                seen.add(actual_name)
                if len(base["candidates"]) < MAX_CANDIDATES:
                    base["candidates"].append(match)
                else:
                    base["candidates_truncated"] = True
        end = start - 1
    return base

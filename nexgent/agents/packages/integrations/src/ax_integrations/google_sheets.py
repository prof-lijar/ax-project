"""Async Sheets v4 transport with a fixed spreadsheet and service-account auth."""

from __future__ import annotations

import asyncio
import re
from urllib.parse import quote, urlsplit

import httpx
from ax_contracts.sheets import (
    AddTab,
    ClearCells,
    DeleteDimension,
    DeleteTab,
    FindAndHighlightAddressRow,
    FindAndHighlightName,
    FindAndHighlightPersonRow,
    ReadCells,
    RenameTab,
    SearchAddress,
    WriteCells,
)

SCOPE = "https://www.googleapis.com/auth/spreadsheets"


class SheetsError(RuntimeError):
    """Safe failure. Mutations with uncertain outcomes must not be replayed blindly."""


def spreadsheet_id(value: str) -> str:
    value = value.strip()
    if value.startswith("https://"):
        parsed = urlsplit(value)
        if parsed.hostname != "docs.google.com":
            raise ValueError("expected a Google Sheets URL")
        match = re.fullmatch(r"/spreadsheets/d/([\w-]+)(?:/.*)?", parsed.path)
        value = match.group(1) if match else ""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("expected a spreadsheet ID or Google Sheets URL")
    return value


def validate_range(value: str) -> None:
    # Require explicit tab and finite rectangle; avoid accidental whole-sheet reads/deletes.
    match = re.fullmatch(
        r"(?:'(?:(?:'')|[^'])+'|[^'!]+)!([A-Z]+)([1-9]\d*)(?::([A-Z]+)([1-9]\d*))?",
        value,
    )
    if not match:
        raise ValueError("use a bounded A1 range with a tab, e.g. 'Sheet 1'!A1:D20")

    def column(label):
        result = 0
        for char in label:
            result = result * 26 + ord(char) - 64
        return result

    left, top, right, bottom = match.groups()
    width = column(right or left) - column(left) + 1
    height = int(bottom or top) - int(top) + 1
    if width < 1 or height < 1 or width * height > 2000:
        raise ValueError("range must contain 1 to 2000 cells in ascending order")


class ServiceAccountToken:
    def __init__(self, filename: str):
        self.filename = filename
        self._credentials = None
        self._lock = asyncio.Lock()

    async def __call__(self) -> str:
        from google.auth.exceptions import GoogleAuthError

        async with self._lock:
            try:
                return await asyncio.to_thread(self._get)
            except (GoogleAuthError, OSError, ValueError):
                raise SheetsError(
                    "Google authentication failed; check service-account configuration"
                ) from None

    def _get(self):
        from google.auth.transport.requests import Request
        from google.oauth2.service_account import Credentials

        if self._credentials is None:
            self._credentials = Credentials.from_service_account_file(
                self.filename,
                scopes=[SCOPE],
            )
        if not self._credentials.valid:
            self._credentials.refresh(Request())
        return self._credentials.token


class GoogleSheetsClient:
    def __init__(
        self,
        sheet: str,
        token_provider,
        *,
        client: httpx.AsyncClient,
        search_sheet_id: int | None = None,
        address_columns: str | None = None,
        person_name_column: str | None = None,
        person_address_column: str | None = None,
        search_start_row: int = 1,
    ):
        self.base = "https://sheets.googleapis.com/v4/spreadsheets/" + spreadsheet_id(
            sheet
        )
        self.token_provider = token_provider
        self.client = client
        self.search_sheet_id = search_sheet_id
        self.address_columns = address_columns
        self.person_name_column = person_name_column
        self.person_address_column = person_address_column
        self.search_start_row = search_start_row

    async def _request(self, method, suffix="", **kwargs):
        token = await self.token_provider()
        try:
            response = await self.client.request(
                method,
                self.base + suffix,
                headers={"Authorization": f"Bearer {token}"},
                **kwargs,
            )
            response.raise_for_status()
            if len(response.content) > 128000:
                raise SheetsError(
                    "Google response exceeded the data limit; narrow the range"
                )
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise SheetsError(
                f"Google Sheets HTTP {exc.response.status_code}; inspect permissions/target before retrying"
            ) from None
        except (httpx.TransportError, ValueError):
            raise SheetsError(
                "Google request outcome unknown; inspect the sheet before replaying any mutation"
            ) from None

    async def metadata(self):
        return await self._request(
            "GET",
            params={
                "fields": "spreadsheetId,properties.title,sheets.properties",
            },
        )

    async def execute(self, action):
        if isinstance(action, FindAndHighlightPersonRow):
            from ax_integrations.sheets_person import find_and_highlight_person

            if self.search_sheet_id is None or self.search_sheet_id < 0:
                raise ValueError("Configure the person-search tab ID")
            return await find_and_highlight_person(
                self,
                sheet_id=self.search_sheet_id,
                name=action.name,
                address=action.address,
                name_column=self.person_name_column,
                address_column=self.person_address_column,
                start_row=self.search_start_row,
            )
        if isinstance(action, (SearchAddress, FindAndHighlightAddressRow)):
            from ax_integrations.sheets_address import (
                highlight_address_row,
                search_address,
            )

            if self.search_sheet_id is None or self.search_sheet_id < 0:
                raise ValueError("configure the address-search tab ID before searching")
            operation = (
                highlight_address_row
                if isinstance(action, FindAndHighlightAddressRow)
                else search_address
            )
            return await operation(
                self,
                sheet_id=self.search_sheet_id,
                address=action.address,
                columns=self.address_columns,
            )
        if isinstance(action, FindAndHighlightName):
            from ax_integrations.sheets_highlight import find_and_highlight

            if self.search_sheet_id is None or self.search_sheet_id < 0:
                raise ValueError(
                    "configure AX768_NAME_SEARCH_SHEET_ID before searching names"
                )
            return await find_and_highlight(
                self, sheet_id=self.search_sheet_id, name=action.name
            )
        if isinstance(action, (ReadCells, WriteCells, ClearCells)):
            validate_range(action.range)
            suffix = "/values/" + quote(action.range, safe="")
            if isinstance(action, ReadCells):
                return await self._request(
                    "GET", suffix, params={"valueRenderOption": "FORMULA"}
                )
            if isinstance(action, ClearCells):
                return await self._request("POST", suffix + ":clear", json={})
            # An update's rectangle must contain every supplied cell, preventing overflow.
            if action.tool == "write_cells":
                match = re.search(r"!([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?$", action.range)
                left, top, right, bottom = match.groups()

                def col(label):
                    n = 0
                    for c in label:
                        n = n * 26 + ord(c) - 64
                    return n

                if len(action.values) > int(bottom or top) - int(top) + 1 or any(
                    len(row) > col(right or left) - col(left) + 1
                    for row in action.values
                ):
                    raise ValueError("values exceed the explicit target range")
            append = action.tool == "append_rows"
            return await self._request(
                "POST" if append else "PUT",
                suffix + (":append" if append else ""),
                params={
                    "valueInputOption": action.input_mode,
                    "includeValuesInResponse": "true",
                },
                json={
                    "range": action.range,
                    "majorDimension": "ROWS",
                    "values": action.values,
                },
            )
        if isinstance(action, AddTab):
            request = {"addSheet": {"properties": {"title": action.title}}}
        elif isinstance(action, RenameTab):
            request = {
                "updateSheetProperties": {
                    "properties": {"sheetId": action.sheet_id, "title": action.title},
                    "fields": "title",
                }
            }
        elif isinstance(action, DeleteTab):
            request = {"deleteSheet": {"sheetId": action.sheet_id}}
        elif isinstance(action, DeleteDimension):
            request = {
                "deleteDimension": {
                    "range": {
                        "sheetId": action.sheet_id,
                        "dimension": "ROWS"
                        if action.tool == "delete_rows"
                        else "COLUMNS",
                        "startIndex": action.start_index,
                        "endIndex": action.end_index,
                    }
                }
            }
        else:
            raise TypeError("unsupported spreadsheet action")
        return await self._request("POST", ":batchUpdate", json={"requests": [request]})

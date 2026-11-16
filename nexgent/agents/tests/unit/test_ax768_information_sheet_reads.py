"""Transport-size and sibling-cancellation regressions for roster reads."""

import asyncio
import json
import re

import httpx
import pytest
from ax_integrations.google_sheets import GoogleSheetsClient, SheetsError

from workflows.ax768.information_sheets import LAYOUTS, Table


@pytest.mark.asyncio
async def test_large_roster_reads_only_names_then_matching_details():
    # A previous 1,000-row address read breaches the real adapter's 128 KB cap.
    address = "경상북도 테스트군 테스트길 100 상세주소 " * 12
    assert len(json.dumps([[address]] * 1000, ensure_ascii=False).encode()) > 128000
    target_rows = {6, 1006, 2005}
    requests = []

    async def upstream(request):
        assert request.method == "GET"
        ranges = request.url.params.get_list("ranges")
        requests.extend(ranges)
        values = []
        for value in ranges:
            match = re.fullmatch(r"'명부'!([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?", value)
            col, start, endcol, end = match.groups()
            start = int(start)
            if end:
                assert col == endcol == "C", (
                    "Nonmatching subscribers must not have their addresses/phones fetched"
                )
                end = int(end)
                assert end - start < 1000
                rows = [
                    ["김하늘" if row in target_rows else "다른가입자"]
                    for row in range(start, end + 1)
                ]
            else:
                assert start in target_rows
                rows = [[{"C": "김하늘", "H": address, "O": "010-0000-1111"}[col]]]
            values.append({"values": rows})
        response = httpx.Response(200, json={"valueRanges": values})
        assert len(response.content) <= 128000
        return response

    async def token():
        return "synthetic-token"

    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as http:
        client = GoogleSheetsClient("test-sheet", token, client=http)
        table = Table(client, 12, 6, LAYOUTS["영덕"])
        table.title = "'명부'"
        table.end = 2005
        rows = await table.find("김하늘")
    assert [row["row"] for row in rows] == [6, 1006, 2005]
    assert all(row["address"] == address for row in rows)
    assert len(requests) == 2 + 3 * 3


@pytest.mark.asyncio
async def test_no_match_does_not_read_details():
    class Client:
        async def _request(self, method, suffix, **kwargs):
            assert kwargs["params"]["ranges"] == ["'명부'!C6:C10"]
            return {"valueRanges": [{"values": [["다른사람"]] * 5}]}

    table = Table(Client(), 12, 6, LAYOUTS["영덕"])
    table.title = "'명부'"
    table.end = 10
    assert await table.find("김하늘") == []


@pytest.mark.asyncio
async def test_failed_page_cancels_and_drains_other_reads():
    sibling_started = asyncio.Event()
    cancelled = []

    class Client:
        async def _request(self, method, suffix, **kwargs):
            a1 = kwargs["params"]["ranges"][0]
            if a1 == "'명부'!C6:C1005":
                await sibling_started.wait()
                raise SheetsError("failed page")
            sibling_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.append(a1)
                raise

    table = Table(Client(), 12, 6, LAYOUTS["영덕"])
    table.title = "'명부'"
    table.end = 3005
    with pytest.raises(SheetsError, match="failed page"):
        await asyncio.wait_for(table.find("김하늘"), 1)
    assert len(cancelled) == 2  # no HTTP operation survives into client shutdown


@pytest.mark.asyncio
async def test_name_change_between_scan_and_details_is_not_absence():
    class Client:
        async def _request(self, method, suffix, **kwargs):
            ranges = kwargs["params"]["ranges"]
            if ":" in ranges[0]:
                return {"valueRanges": [{"values": [["김하늘"]]}]}
            return {
                "valueRanges": [
                    {"values": [["다른사람"]]},
                    {"values": [["주소"]]},
                    {"values": [["010-0000-1111"]]},
                ]
            }

    table = Table(Client(), 12, 6, LAYOUTS["영덕"])
    table.title = "'명부'"
    table.end = 6
    with pytest.raises(SheetsError, match="이름이 변경"):
        await table.find("김하늘")

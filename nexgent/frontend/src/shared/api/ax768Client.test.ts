import { afterEach, describe, expect, it, vi } from "vitest";
import { ax768Client, isSheetUrl } from "./ax768Client";

export const fixture = {
  id: "run-1", case_id: "4.2", status: "completed", outcome: "found", response: "일치 행: 44",
  started_at: "2026-11-04T00:00:00Z", duration_ms: 1230, city: "울진군", sheet_alias: "uljin-users",
  sheet_title: "명부", selected_row: 44, name: "김순옥", address: "울진북로 164",
  sheet_url: "https://docs.google.com/spreadsheets/d/fixed/edit#gid=42&range=A44",
  highlighted_range: null, stored_verified: null, visible_verified: null,
  overridden_cells: [], overridden_cell_count: 0, match_count: 1, matches: [], attempts: []
};
afterEach(() => vi.unstubAllGlobals());
describe("AX768 API", () => {
  it("submits an explicit case and normalizes a real response", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(fixture)));
    vi.stubGlobal("fetch", fetch);
    expect(await ax768Client.run("4.2", " message ")).toEqual(fixture);
    expect(fetch.mock.calls[0][0].toString()).toContain("/api/ax768/runs");
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ case_id: "4.2", message: "message" });
  });
  it.each([502, 504])("does not retry an uncertain %i response", async status => {
    const fetch = vi.fn().mockResolvedValue(new Response("{}", { status })); vi.stubGlobal("fetch", fetch);
    await expect(ax768Client.run("2.2", "후포로 158")).rejects.toMatchObject({ outcome: "unknown" });
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("rejects mismatched or malformed upstream results", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...fixture, case_id: "6.2" }))));
    await expect(ax768Client.run("4.2", "text")).rejects.toMatchObject({ outcome: "unknown" });
  });
  it("rejects a blank message before dispatch", async () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    await expect(ax768Client.run("4.2", " ")).rejects.toMatchObject({ outcome: "blocked" });
    expect(fetch).not.toHaveBeenCalled();
  });
  it("restricts sheet links to Google Sheets", () => {
    expect(isSheetUrl(fixture.sheet_url)).toBe(true);
    expect(isSheetUrl("https://docs.google.com.evil.test/spreadsheets/d/a/edit")).toBe(false);
    expect(isSheetUrl("javascript:alert(1)")).toBe(false);
  });
});


describe("IMEI API response", () => {
  it.each([true, false])("preserves verified connected=%s receipt", async connected => {
    const result = {...fixture, case_id: "imei", outcome: connected ? "connected" : "disconnected", imei: "861212072106726", imei_column: "Z",
      ping: {imei: "861212072106726", sn: "00300016", connected, fresh: connected, signal_label: "보통", rssi: 22, elapsed_ms: 1000}};
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(result))));
    expect((await ax768Client.run("imei", "김순옥님 신호확인요.")).ping?.sn).toBe("00300016");
  });
  it("rejects connection results without evidence", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({...fixture, case_id: "imei", outcome: "connected"}))));
    await expect(ax768Client.run("imei", "김순옥님 신호확인요.")).rejects.toThrow();
  });
});

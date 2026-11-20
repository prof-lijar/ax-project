import { afterEach, describe, expect, it, vi } from "vitest";
import { runAx768Workflow } from "./ax768WorkflowClient";
const stage = { status: "found", row: 44, sheet_alias: "uljin-users", city: "울진군", sheet_title: "명부", name: "김순옥", address: "울진북로164", reason: null, sheet_url: "https://docs.google.com/spreadsheets/d/sheet/edit#gid=7&range=A44" };
const signal = {status: "connected", imei_column: "AA", imei: "861212072106726", sn: "00300016", connected: true, fresh: true, signal_label: "보통", rssi: 22, reason: null};
const memberNote = {status: "saved", member_id: 12, name: "김순옥", address: "울진북로164", note: "2026-11-04 [현지관리자 방문] 기기위치조정", verified: true, candidates: []};
const fixture = {member_note: memberNote, signal, workflow_id: "device_adjustment_power", id: "run", started_at: "2026-11-04", duration_ms: 100, status: "completed", response: "일치", parsed: { name: "김순옥", lookup_name: "김순옥", address: "울진북로164", mode: "name_address" }, roster: stage, as_lookup: stage, candidates: [], notices: [], attempts: [], as_update: {status: "updated", row: 44, date: "2026-11-04", changes: [{column: "S", value: "처리완료"}, {column: "X", value: "2026-11-04"}], y_action: "unchanged", verified: true, reason: "saved"} };
afterEach(() => vi.unstubAllGlobals());
describe("Unified AX768 workflow API", () => {
  it.each(["", "information_update", "device_collection", "device_replacement", "device_loss", "new_installation"] as const)("blocks missing or unavailable workflow %s before fetch", async workflowId => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    await expect(runAx768Workflow(workflowId, "김순옥님 신호확인요.")).rejects.toThrow(workflowId ? "coming soon" : "select a workflow");
    expect(fetch).not.toHaveBeenCalled();
  });
  it("submits text and a selected name without requesting a region", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(fixture))); vi.stubGlobal("fetch", fetch);
    expect(await runAx768Workflow("device_adjustment_power", " input ", "김영호")).toEqual(fixture);
    expect(fetch.mock.calls[0][0].toString()).toContain("/api/ax768/runs");
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({workflow_id: "device_adjustment_power", message: "input", confirmed_name: "김영호"});
  });
  it.each([409, 422, 502, 504])("shows failure %i without retry", async status => {
    const fetch = vi.fn().mockResolvedValue(new Response("{}", {status})); vi.stubGlobal("fetch", fetch);
    await expect(runAx768Workflow("device_adjustment_power", "text")).rejects.toThrow();
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it.each([
    {...fixture, as_lookup: {...stage, status: "not_found"}},
    {...fixture, as_lookup: {...stage, sheet_url: "javascript:alert(1)"}},
    {...fixture, workflow_id: "device_loss"},
    {...fixture, workflow_id: undefined},
    {...fixture, candidates: null},
    {...fixture, member_note: undefined},
    {...fixture, member_note: null},
    {...fixture, member_note: {...memberNote, verified: false}},
    {...fixture, member_note: {...memberNote, address: "다른길 1"}},
    {...fixture, member_note: {...memberNote, note: "2026-11-05 [현지관리자 방문] 기기위치조정"}},
    {...fixture, signal: undefined},
    {...fixture, signal: {...signal, fresh: false}},
    {...fixture, signal: {...signal, imei_column: "Z"}},
    {...fixture, signal: {...signal, connected: false}},
    {...fixture, parsed: {}},
    {...fixture, as_update: {...fixture.as_update, verified: false}},
    {...fixture, as_update: {...fixture.as_update, row: 999}},
    {...fixture, as_update: {...fixture.as_update, changes: []}}
  ])("rejects malformed or unsafe result evidence", async body => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body))));
    await expect(runAx768Workflow("device_adjustment_power", "text")).rejects.toThrow("could not be retrieved");
  });

  it.each([
    ["uljin-users", "AA", "Z"],
    ["gwangmyeon-users", "W", "V"],
    ["yeongdeok-users", "Z", "Y"],
  ])("uses the verified IMEI column for %s and rejects its S/N column", async (alias, column, serialColumn) => {
    const body = {...fixture, roster: {...stage, sheet_alias: alias}, signal: {...signal, imei_column: column}};
    const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(body)))
      .mockResolvedValueOnce(new Response(JSON.stringify({...body, signal: {...signal, imei_column: serialColumn}})));
    vi.stubGlobal("fetch", fetch);
    expect((await runAx768Workflow("device_adjustment_power", "text")).signal.imei_column).toBe(column);
    await expect(runAx768Workflow("device_adjustment_power", "text")).rejects.toThrow("could not be retrieved");
  });

  it("keeps the roster receipt when AS fails", async () => {
    const partial = {...fixture, member_note: null, status: "failed", as_lookup: {...stage, status: "failed", row: null, sheet_url: null}, as_update: {...fixture.as_update, status: "skipped", verified: false}};
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(partial))));
    expect((await runAx768Workflow("device_adjustment_power", "text")).roster.row).toBe(44);
  });
  it("returns a disconnected report without an AS update", async () => {
    const body = {...fixture, member_note: null, status: "disconnected", signal: {...signal, status: "disconnected", connected: false, fresh: false},
      as_update: {status: "skipped", row: null, date: null, changes: [], y_action: null, verified: false, reason: "disconnected"}};
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body))));
    expect((await runAx768Workflow("device_adjustment_power", "text")).signal.sn).toBe("00300016");
  });
  it("completes general notes when no AS row exists", async () => {
    const body = {...fixture, as_lookup: {...stage, status: "not_found", row: null, sheet_url: null}, as_update: {status: "skipped", row: null, date: null, changes: [], y_action: null, verified: false, reason: null}};
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body))));
    expect((await runAx768Workflow("device_adjustment_power", "text")).member_note?.verified).toBe(true);
  });
  it("keeps verified AS results when a member write is uncertain", async () => {
    const body = {...fixture, status: "failed", member_note: {...memberNote, status: "unknown", verified: false}};
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body))));
    const result = await runAx768Workflow("device_adjustment_power", "text");
    expect(result.as_update.verified).toBe(true);
    expect(result.member_note?.status).toBe("unknown");
  });
  it("rejects blank input without calling the server", async () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    await expect(runAx768Workflow("device_adjustment_power", " ")).rejects.toThrow(); expect(fetch).not.toHaveBeenCalled();
  });
});

it.each([
  ["울진군 금강송면 왕피길 83-15", true],
  ["경상북도 울진군 금강송면 왕피길 83-15", true],
  ["영덕군 금강송면 왕피길 83-15", false],
  ["울진군 금강송면 왕피길 83-16", false],
  ["울진군 북면 왕피길 83-15", false],
])("validates the reported member address %s", async (address, accepted) => {
  const body = {...fixture, roster: {...stage, name: "정영자", address: "금강송면 왕피길 83-15"}, member_note: {...memberNote, name: "정영자", address}};
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body))));
  if (accepted) expect((await runAx768Workflow("device_adjustment_power", "text")).member_note?.address).toBe(address);
  else await expect(runAx768Workflow("device_adjustment_power", "text")).rejects.toThrow();
});

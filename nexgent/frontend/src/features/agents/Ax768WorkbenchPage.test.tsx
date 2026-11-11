import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Ax768WorkbenchPage, Ax768ResultView } from "./Ax768WorkbenchPage";
import { useAx768Store, type Ax768Run } from "../../shared/state/useAx768Store";
import { useLanguage } from "../../shared/i18n";
import { AX768_CASES, type Ax768Result } from "../../shared/api/ax768Client";

// SSR reads Zustand's immutable initial snapshot. Supply the test's current
// store snapshot without changing the production hook or adding a DOM runtime.
vi.mock("../../shared/state/useAx768Store", async importOriginal => {
  const actual = await importOriginal<typeof import("../../shared/state/useAx768Store")>();
  return { ...actual, useAx768Store: Object.assign(() => actual.useAx768Store.getState(), actual.useAx768Store) };
});

afterEach(() => { vi.restoreAllMocks(); useAx768Store.getState().reset(); useLanguage.setState({ language: "ko" }); });
describe("운영시트에이젠트 workspace", () => {
  it("shows nine cases, editable input and example action", () => {
    useLanguage.setState({ language: "en" });
    const html = renderToStaticMarkup(<Ax768WorkbenchPage />);
    expect((html.match(/<select[^>]*id="ax-case"[\s\S]*?<\/select>/)?.[0].match(/<option /g) ?? [])).toHaveLength(9);
    expect(html).toContain('id="ax-message"'); expect(html).toContain("Use example");
    expect(html).toContain("Your next match starts here"); expect(html).toContain("This session only");
  });
  it.each(AX768_CASES.filter(c => c.id !== "member_note"))("offers search only for case $id", c => {
    useLanguage.setState({ language: "en" });
    useAx768Store.setState({ selectedCase: c.id });
    const html = renderToStaticMarkup(<Ax768WorkbenchPage />);
    expect(c.writes).toBe(false);
    expect(html).toContain(c.id === "imei" ? "Signal check · no sheet changes" : "Search only · no sheet changes");
    expect(html).not.toContain("Search and apply yellow");
  });
  it("renders an active request as loading with elapsed time", () => {
    useLanguage.setState({ language: "en" });
    useAx768Store.setState({ active: { id: "a", caseId: "4.2", message: "text", startedAt: Date.now(), result: null, error: null, outcome: null } });
    const html = renderToStaticMarkup(<Ax768WorkbenchPage />);
    expect(html).toContain("운영시트에이젠트 is working"); expect(html).toContain("Running…");
    expect(html).toContain('aria-live="polite"'); expect(html).toContain("disabled");
  });
  it("does not claim visible yellow when stored color is overridden", () => {
    useLanguage.setState({ language: "en" });
    const run = { id: "a", caseId: "2.3", message: "text", startedAt: Date.now(), error: null, outcome: null,
      result: { outcome: "highlighted_with_warnings", selected_row: 985, stored_verified: true, visible_verified: false,
        overridden_cells: ["C985", "O985"], overridden_cell_count: 2, attempts: [], match_count: 1,
        response: "Stored yellow", duration_ms: 1200 } as unknown as Ax768Result } satisfies Ax768Run;
    const html = renderToStaticMarkup(<Ax768ResultView run={run} />);
    expect(html).toContain("Yellow saved · display overridden"); expect(html).toContain("Not confirmed");
    expect(html).toContain("C985"); expect(html).toContain("may not appear");
  });
});


describe("IMEI signal result", () => {
  it.each([true, false])("shows the returned S/N and connected=%s response", connected => {
    useLanguage.setState({language: "en"});
    const response = connected ? "S/N 00300016 신호 확인되었습니다." : "S/N 00300016 전원 연결 및 기기위치 확인해주세요.";
    const run = {id: "imei", caseId: "imei", message: "김순옥님 신호확인요.", startedAt: 0, error: null, outcome: null,
      result: {outcome: connected ? "connected" : "disconnected", response, selected_row: 80, imei: "861212072106726", imei_column: "Z",
        ping: {sn: "00300016", connected, signal_label: "보통", rssi: 22}, attempts: [], duration_ms: 1000} as unknown as Ax768Result} satisfies Ax768Run;
    const html = renderToStaticMarkup(<Ax768ResultView run={run}/>);
    expect(html).toContain(response); expect(html).toContain("861212072106726"); expect(html).toContain("00300016"); expect(html).toContain("IMEI (Z)");
  });
});

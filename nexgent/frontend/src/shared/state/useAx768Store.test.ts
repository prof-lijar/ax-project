import { afterEach, describe, expect, it, vi } from "vitest";
import { ax768Client, Ax768ClientError, type Ax768Result } from "../api/ax768Client";
import { useAx768Store } from "./useAx768Store";

afterEach(() => { useAx768Store.getState().reset(); vi.restoreAllMocks(); });
function prepare() { useAx768Store.getState().setDraft("울진북로 164 김순옥님 신호확인요."); }
function response(): Ax768Result { return { id: "a", outcome: "found" } as Ax768Result; }
describe("AX768 session state", () => {
  it("preserves separate drafts by case", () => {
    prepare(); useAx768Store.getState().selectCase("6.2"); useAx768Store.getState().setDraft("왕피길83-15,정영자,수신확인요");
    expect(useAx768Store.getState().drafts["4.2"]).toContain("김순옥");
  });
  it("prevents duplicate submissions while running", async () => {
    let finish!: (result: Ax768Result) => void;
    const call = vi.spyOn(ax768Client, "run").mockReturnValue(new Promise(resolve => { finish = resolve; }));
    prepare(); const pending = useAx768Store.getState().run();
    await useAx768Store.getState().run(); expect(call).toHaveBeenCalledTimes(1);
    expect(useAx768Store.getState().active).not.toBeNull();
    finish(response()); await pending;
    expect(useAx768Store.getState().history).toHaveLength(1);
  });
  it("drops late results after logout or account change", async () => {
    let finish!: (result: Ax768Result) => void;
    vi.spyOn(ax768Client, "run").mockReturnValue(new Promise(resolve => { finish = resolve; }));
    prepare(); const pending = useAx768Store.getState().run();
    useAx768Store.getState().reset(); finish(response()); await pending;
    expect(useAx768Store.getState().history).toEqual([]); expect(useAx768Store.getState().drafts).toEqual({});
  });
  it("keeps only 20 session results and does not retry failures", async () => {
    const call = vi.spyOn(ax768Client, "run").mockRejectedValue(new Ax768ClientError("Inspect the sheet"));
    prepare(); for (let i = 0; i < 21; i++) await useAx768Store.getState().run();
    expect(call).toHaveBeenCalledTimes(21); expect(useAx768Store.getState().history).toHaveLength(20);
    expect(useAx768Store.getState().history[0].outcome).toBe("unknown");
  });
});

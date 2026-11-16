import { afterEach, describe, expect, it, vi } from "vitest";
import { extractWorkflowDraft } from "./ax768WorkflowExtraction";
const page = { filename: "info.png", text: "이름: 김순옥\n주소: 울진북로 164\n연락처: 010-0000-1234\n기기: 00300016", confidence: 95 };
const signal = () => new AbortController().signal;
const field = { label: "보호자 연락처", value: "010-0000-1234", source_index: 0, uncertain: false };
function result(fields: unknown[]) { return new Response(JSON.stringify({ workflow_id: "information_update", extraction_version: "1", fields })); }
afterEach(() => vi.unstubAllGlobals());

describe("workflow-specific extraction", () => {
  it("keeps all raw text before selection without inserting a device request", async () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    const draft = await extractWorkflowDraft("", [page], "", signal());
    expect(draft.message).toBe(page.text); expect(draft.message).not.toContain("신호확인"); expect(fetch).not.toHaveBeenCalled();
  });
  it("preserves the device-specific extractor and avoids model calls", async () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    const draft = await extractWorkflowDraft("device_adjustment_power", [page], "", signal());
    expect(draft.message).toContain("이름: 김순옥\n주소: 울진북로 164\n요청: 신호확인"); expect(fetch).not.toHaveBeenCalled();
  });
  it("uses agent-discovered fields and preserves raw source material", async () => {
    const fields = [field, { ...field, label: "S/N", value: "00300016" }];
    const fetch = vi.fn().mockResolvedValue(result(fields)); vi.stubGlobal("fetch", fetch);
    const draft = await extractWorkflowDraft("information_update", [page], "", signal());
    expect(draft.message).toContain("보호자 연락처: 010-0000-1234"); expect(draft.message).toContain("S/N: 00300016");
    expect(draft.message).not.toContain("신호확인"); expect(draft.message).not.toContain(page.filename); expect(draft.structured).toBe(true); expect(draft.pages).toEqual([page]);
    expect(fetch.mock.calls[0][0]).toBe("/api/ax768/workflow/extract");
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ workflow_id: "information_update", sources: [{ text: page.text }] });
  });
  it("supports text-only analysis and keeps uncertain values separate by source", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(result([{ ...field, uncertain: true }])));
    const draft = await extractWorkflowDraft("information_update", [], page.text, signal());
    expect(draft.original).toBe(page.text); expect(draft.message).toContain("(확인 필요)"); expect(draft.needsReview).toBe(true);
  });
  it("does not reinsert raw noise after a successful empty extraction", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(result([])));
    const draft = await extractWorkflowDraft("information_update", [page], "", signal());
    expect(draft.message).toBe(""); expect(draft.noInformation).toBe(true); expect(draft.needsReview).toBe(false); expect(draft.pages).toEqual([page]);
  });
  it.each([{ ...field, value: "invented" }, { ...field, source_index: 3 }, { ...field, uncertain: "false" }])("rejects invalid agent results", async invalid => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(result([invalid])));
    await expect(extractWorkflowDraft("information_update", [page], "", signal())).rejects.toThrow("Information extraction failed");
  });
  it("omits an ignored source without mixing two subjects or reintroducing chat noise", async () => {
    const people = { filename: "chat.png", text: "김하늘님\n테스트항길 50-1\n이도윤님\n며느님 추가\n010-0000-2222", confidence: 95 };
    const noise = { filename: "chrome.png", text: "H\n[\nsg 744", confidence: 95 };
    const fields = [
      { label: "김하늘 · 주소", value: "테스트항길 50-1", source_index: 0, uncertain: false },
      { label: "이도윤 · 보호자 관계", value: "며느님", source_index: 0, uncertain: false },
      { label: "이도윤 · 추가 연락처", value: "010-0000-2222", source_index: 0, uncertain: false }
    ];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(result(fields)));
    const draft = await extractWorkflowDraft("information_update", [people, noise], "", signal());
    expect(draft.message).toBe("김하늘 · 주소: 테스트항길 50-1\n이도윤 · 보호자 관계: 며느님\n이도윤 · 추가 연락처: 010-0000-2222");
    expect(draft.noInformation).toBe(false); expect(draft.pages).toEqual([people, noise]);
  });
  it("rejects over-limit sources without sending or truncating", async () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    await expect(extractWorkflowDraft("information_update", [], "x".repeat(8001), signal())).rejects.toThrow("8,000"); expect(fetch).not.toHaveBeenCalled();
  });
});

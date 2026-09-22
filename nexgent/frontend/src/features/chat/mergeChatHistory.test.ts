import { describe, expect, it } from "vitest";
import { createConversation, type ChatMessage } from "../../shared/state/useChatStore";
import { mergeChatHistory, reconcileRunId } from "./mergeChatHistory";

const answer: ChatMessage = { id: "answer", role: "assistant", content: "SAT plan", status: "complete", position: 2 };

describe("independent chat history responses", () => {
  it.each(["complete", "stopped", "failed"] as const)("preserves a %s reply when old waiting history arrives", status => {
    const current = { ...answer, status };
    expect(mergeChatHistory([current], [{ ...answer, content: "", status: "waiting" }])).toEqual([current]);
  });
  it("does not rewind streaming content, but accepts a newer final answer", () => {
    const current = { ...answer, status: "streaming" as const };
    expect(mergeChatHistory([current], [{ ...current, content: "SAT" }])).toEqual([current]);
    expect(mergeChatHistory([current], [{ ...answer, content: "Corrected final" }])[0].content).toBe("Corrected final");
  });
  it("accepts longer streaming history on reconnect", () => {
    expect(mergeChatHistory([{ ...answer, content: "SAT", status: "streaming" }],
      [{ ...answer, status: "streaming" }])[0].content).toBe("SAT plan");
  });
  it("keeps positioned live replies missing from stale pages and orders pagination without duplicates", () => {
    const user: ChatMessage = { id: "user", role: "user", content: "Plan", position: 1 };
    const previous: ChatMessage = { id: "previous", role: "assistant", content: "Earlier", position: 0 };
    expect(mergeChatHistory([user, answer], [previous, user])).toEqual([previous, user, answer]);
  });
  it("adds server positions without discarding a completed reply", () => {
    expect(mergeChatHistory([{ ...answer, position: undefined }],
      [{ ...answer, content: "", status: "waiting" }])).toEqual([answer]);
  });
  it("keeps a submitted user message before its positioned assistant snapshot", () => {
    const user: ChatMessage = { id: "user", role: "user", content: "Plan" };
    const earlier: ChatMessage = { id: "earlier", role: "assistant", content: "Earlier", position: 0 };
    expect(mergeChatHistory([user, answer], [earlier])).toEqual([earlier, user, answer]);
  });
  it("does not resurrect a finished run from stale list or detail metadata", () => {
    const chat = { ...createConversation(), runId: null, settledRunIds: ["old"] };
    expect(reconcileRunId(chat, "old")).toBeNull();
    expect(reconcileRunId(chat, "new")).toBe("new");
    expect(reconcileRunId({ ...chat, runId: "new" }, "old")).toBe("new");
    expect(reconcileRunId({ ...chat, runId: "new" }, null)).toBe("new");
  });
});

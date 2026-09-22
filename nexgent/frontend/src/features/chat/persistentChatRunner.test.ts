import { beforeEach, describe, expect, it, vi } from "vitest";
import { chatHistoryClient, type RunSnapshot } from "../../shared/api/chatHistoryClient";
import { createConversation, useChatStore } from "../../shared/state/useChatStore";
import { createPersistentChatRunner } from "./persistentChatRunner";

const result = { conversation_id: "saved", user_message_id: "user", assistant_message_id: "assistant", run_id: "run" };
const snapshot = (status: RunSnapshot["status"], content = "hello", revision = 1): RunSnapshot => ({
  ...result, status, revision, cancel_requested: false, error_code: null,
  message: { id: "assistant", role: "assistant", content, status: status === "completed" ? "complete" : "streaming" }
});
function fixture() {
  let push!: (s: RunSnapshot) => void;
  let close!: () => void;
  const client = { ...chatHistoryClient,
    submit: vi.fn().mockResolvedValue(result),
    run: vi.fn().mockResolvedValue(snapshot("running")),
    cancel: vi.fn().mockResolvedValue({}),
    observe: vi.fn((_id: string, signal: AbortSignal, update: (s: RunSnapshot) => void) => {
      push = update;
      return new Promise<void>(resolve => { close = resolve; signal.addEventListener("abort", () => resolve(), { once: true }); });
    })
  };
  return { client, push: (s: RunSnapshot) => push(s), close: () => close() };
}
function current() { const s = useChatStore.getState(); return s.conversations.find(c => c.id === s.activeId)!; }
beforeEach(() => {
  vi.stubGlobal("window", { dispatchEvent: vi.fn(), location: { pathname: "/settings" }, history: { replaceState: vi.fn() } });
  const chat = createConversation(); chat.draft = "hello";
  useChatStore.setState({ conversations: [chat], activeId: chat.id, activeRequest: null });
});
describe("Saved chat lifecycle", () => {
  it("saves server IDs and follows a reply without duplicate messages", async () => {
    const f = fixture(), runner = createPersistentChatRunner(f.client), id = current().id;
    await runner.send(id);
    await vi.waitFor(() => expect(f.client.observe).toHaveBeenCalled());
    expect(current().serverId).toBe("saved");
    f.push(snapshot("running", "partial", 2));
    f.push(snapshot("running", "partial", 2));
    expect(current().messages).toHaveLength(2);
    f.push(snapshot("completed", "done", 3)); f.close();
    expect(current().messages[1].content).toBe("done");
    expect(current().runId).toBeNull(); runner.detach();
    expect(current().settledRunIds).toEqual(["run"]);
    runner.watch!(id, "run");
    expect(f.client.run).toHaveBeenCalledTimes(1);
  });
  it("detaches on logout without cancelling and ignores late output", async () => {
    const f = fixture(), runner = createPersistentChatRunner(f.client);
    await runner.send(current().id);
    await vi.waitFor(() => expect(f.client.observe).toHaveBeenCalled());
    runner.detach();
    const next = createConversation();
    useChatStore.setState({ conversations: [next], activeId: next.id });
    f.push(snapshot("completed", "old account secret", 4));
    expect(current().messages).toEqual([]);
    expect(f.client.cancel).not.toHaveBeenCalled();
  });
  it("explicit Stop requests server cancellation", async () => {
    const f = fixture(), runner = createPersistentChatRunner(f.client);
    await runner.send(current().id);
    runner.stop(); await vi.waitFor(() => expect(f.client.cancel).toHaveBeenCalledWith("run"));
    runner.detach();
  });
  it("retains the submission key for retries after an ambiguous network failure", async () => {
    const f = fixture(), runner = createPersistentChatRunner(f.client);
    f.client.submit.mockRejectedValueOnce(new Error("network"));
    await runner.send(current().id);
    const key = current().submissionKey;
    expect(current().draft).toBe("hello");
    await runner.send(current().id);
    expect(f.client.submit.mock.calls[1][4]).toBe(key);
    runner.detach();
  });
  it("can reconnect to a reply submitted from another browser", async () => {
    const f = fixture(), runner = createPersistentChatRunner(f.client);
    useChatStore.getState().patchChat(current().id, { serverId: "saved", runId: "run" });
    f.client.run.mockResolvedValue(snapshot("completed", "finished while away"));
    runner.watch!(current().id, "run");
    await vi.waitFor(() => expect(current().messages[0]?.content).toBe("finished while away"));
    expect(f.client.submit).not.toHaveBeenCalled(); runner.detach();
  });
});

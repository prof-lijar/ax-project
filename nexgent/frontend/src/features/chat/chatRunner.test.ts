import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  agentCatalogClient,
  RAG_CHAT_GRAPH_ID
} from "../../shared/api/agentCatalogClient";
import { agentServerClient } from "../../shared/api/agentServerClient";
import {
  createConversation,
  useChatStore
} from "../../shared/state/useChatStore";
import { createChatRunner } from "./chatRunner";

function controlledClient() {
  let resolve!: (value: string) => void;
  let reject!: (reason: Error) => void;
  let onResponse: (value: string) => void = () => {};
  let signal: AbortSignal | undefined;
  const streamChat = vi.fn<typeof agentServerClient.streamChat>(
    (_prompt, options) => {
      onResponse = options?.onResponse ?? (() => {});
      signal = options?.signal;
      return new Promise<string>((done, fail) => {
        resolve = done;
        reject = fail;
      });
    }
  );
  const client = {
    ...agentServerClient,
    streamChat,
    streamRagChat: vi
      .fn<typeof agentServerClient.streamRagChat>()
      .mockResolvedValue("RAG reply")
  };
  return {
    client,
    chunk: (value: string) => onResponse(value),
    resolve: (value: string) => resolve(value),
    reject: (error: Error) => reject(error),
    signal: () => signal
  };
}
function current(id = useChatStore.getState().activeId) {
  return useChatStore.getState().conversations.find((c) => c.id === id)!;
}
beforeEach(() => {
  const conversation = createConversation();
  conversation.draft = "First question";
  useChatStore.setState({
    conversations: [conversation],
    activeId: conversation.id,
    activeRequest: null
  });
});

describe("Chat request lifecycle", () => {
  it("streams into its original chat after switching and blocks duplicate submissions", async () => {
    const mock = controlledClient();
    const runner = createChatRunner(mock.client);
    const first = current().id;
    const pending = runner.send(first);
    mock.chunk("Partial");
    const second = useChatStore.getState().newChat();
    useChatStore.getState().patchChat(second, { draft: "Second question" });
    await runner.send(second);
    expect(mock.client.streamChat).toHaveBeenCalledTimes(1);
    mock.chunk("Complete reply");
    mock.resolve("Complete reply");
    await pending;
    expect(current(first).messages[1]).toMatchObject({
      content: "Complete reply",
      status: "complete",
      speaker: "AX"
    });
    expect(current(second).messages).toEqual([]);
    expect(current(second).draft).toBe("Second question");
    expect(useChatStore.getState().activeRequest).toBeNull();
  });
  it("stops immediately and ignores late chunks and completion", async () => {
    const mock = controlledClient();
    const runner = createChatRunner(mock.client);
    const pending = runner.send(current().id);
    mock.chunk("Keep this");
    runner.stop();
    expect(mock.signal()?.aborted).toBe(true);
    mock.chunk("Ignore this");
    mock.resolve("Ignore this too");
    await pending;
    expect(current().messages[1]).toMatchObject({
      content: "Keep this",
      status: "stopped"
    });
    expect(useChatStore.getState().activeRequest).toBeNull();
  });
  it("cannot resurrect a deleted conversation", async () => {
    const mock = controlledClient();
    const runner = createChatRunner(mock.client);
    const id = current().id;
    const pending = runner.send(id);
    runner.stop();
    useChatStore.getState().deleteChat(id);
    mock.chunk("late");
    mock.resolve("late");
    await pending;
    expect(current().messages).toEqual([]);
    expect(useChatStore.getState().conversations.some((c) => c.id === id)).toBe(
      false
    );
  });
  it("retains partial replies and recovery files without replacing a newer draft", async () => {
    const mock = controlledClient();
    const runner = createChatRunner(mock.client);
    const file = new File(["contents"], "notes.txt");
    useChatStore.getState().patchChat(current().id, { files: [file] });
    const pending = runner.send(current().id);
    mock.chunk("Partial reply");
    useChatStore.getState().patchChat(current().id, { draft: "A newer draft" });
    mock.reject(new Error("Disconnected"));
    await pending;
    expect(current()).toMatchObject({
      draft: "A newer draft",
      error: "Disconnected",
      recovery: { prompt: "First question", files: [file] }
    });
    expect(current().messages[1]).toMatchObject({
      content: "Partial reply",
      status: "failed"
    });
    expect(mock.client.streamChat.mock.calls[0][1]?.files).toEqual([file]);
  });
  it("routes RAG through the unchanged text-only client and preserves speaker identity", async () => {
    const mock = controlledClient();
    const runner = createChatRunner(mock.client);
    const rag = (await agentCatalogClient.listAgents()).find(
      (a) => a.graphId === RAG_CHAT_GRAPH_ID
    )!;
    useChatStore.getState().chooseAgent(current().id, rag);
    await runner.send(current().id);
    useChatStore.getState().chooseAgent(current().id, null);
    expect(mock.client.streamChat).not.toHaveBeenCalled();
    expect(mock.client.streamRagChat.mock.calls[0][0]).toBe("First question");
    expect(mock.client.streamRagChat.mock.calls[0][1]).not.toHaveProperty(
      "files"
    );
    expect(current().messages[1]).toMatchObject({
      content: "RAG reply",
      speaker: "RAG Agent"
    });
  });
  it("does not let an old cancelled request clear a newer request", async () => {
    const old = controlledClient();
    const newer = controlledClient();
    const streamChat = vi
      .fn<typeof agentServerClient.streamChat>()
      .mockImplementationOnce(old.client.streamChat)
      .mockImplementationOnce(newer.client.streamChat);
    const runner = createChatRunner({ ...old.client, streamChat });
    const first = runner.send(current().id);
    runner.stop();
    useChatStore.getState().patchChat(current().id, { draft: "New request" });
    const second = runner.send(current().id);
    old.resolve("late");
    await first;
    expect(useChatStore.getState().activeRequest).not.toBeNull();
    newer.resolve("New reply");
    await second;
    expect(current().messages[3]).toMatchObject({
      content: "New reply",
      status: "complete"
    });
  });
});

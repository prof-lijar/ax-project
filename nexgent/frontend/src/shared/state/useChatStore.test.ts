import { beforeEach, describe, expect, it } from "vitest";
import {
  agentCatalogClient,
  RAG_CHAT_GRAPH_ID
} from "../api/agentCatalogClient";
import { createConversation, useChatStore } from "./useChatStore";

beforeEach(() => {
  const conversation = createConversation();
  useChatStore.setState({
    conversations: [conversation],
    activeId: conversation.id,
    activeRequest: null
  });
});

describe("session conversations", () => {
  it("reuses an empty conversation, but preserves a draft when starting another", () => {
    const store = useChatStore.getState();
    const first = store.activeId;
    expect(store.newChat()).toBe(first);
    store.patchChat(first, { draft: "Keep this draft" });
    const second = store.newChat();
    expect(second).not.toBe(first);
    expect(
      useChatStore.getState().conversations.find((c) => c.id === first)?.draft
    ).toBe("Keep this draft");
  });
  it("isolates messages, files, errors and scroll positions across chats", () => {
    const store = useChatStore.getState();
    const first = store.activeId;
    const file = new File(["notes"], "notes.txt");
    store.patchChat(first, {
      files: [file],
      error: "Failed",
      scrollTop: 150,
      following: false
    });
    store.appendMessage(first, {
      id: "user",
      role: "user",
      content: "First prompt"
    });
    const second = store.newChat();
    store.patchChat(second, { draft: "Second prompt" });
    store.selectChat(first);
    expect(
      useChatStore.getState().conversations.find((c) => c.id === first)
    ).toMatchObject({
      files: [file],
      error: "Failed",
      scrollTop: 150,
      following: false,
      title: "First prompt"
    });
    expect(
      useChatStore.getState().conversations.find((c) => c.id === second)
    ).toMatchObject({
      files: [],
      messages: [],
      error: null,
      draft: "Second prompt"
    });
  });
  it("titles the first prompt and preserves an explicit rename", () => {
    const store = useChatStore.getState();
    store.appendMessage(store.activeId, {
      id: "one",
      role: "user",
      content: "A long\n" + "prompt ".repeat(20)
    });
    expect(useChatStore.getState().conversations[0].title).toHaveLength(48);
    store.renameChat(store.activeId, "  My project  ");
    store.appendMessage(store.activeId, {
      id: "two",
      role: "user",
      content: "Another question"
    });
    expect(useChatStore.getState().conversations[0].title).toBe("My project");
    store.renameChat(store.activeId, "   ");
    expect(useChatStore.getState().conversations[0].title).toBe("My project");
  });
  it("selects the most recently used remaining chat and always leaves one chat", () => {
    const store = useChatStore.getState();
    const first = store.activeId;
    store.patchChat(first, { draft: "one", updatedAt: 1 });
    const second = store.newChat();
    store.patchChat(second, { draft: "two", updatedAt: 3 });
    const third = store.newChat();
    store.deleteChat(third);
    expect(useChatStore.getState().activeId).toBe(second);
    store.deleteChat(second);
    store.deleteChat(first);
    expect(useChatStore.getState().conversations).toHaveLength(1);
    expect(useChatStore.getState().conversations[0].messages).toEqual([]);
  });
  it("clears only the selected chat's pending files when choosing RAG", async () => {
    const rag = (await agentCatalogClient.listAgents()).find(
      (a) => a.graphId === RAG_CHAT_GRAPH_ID
    )!;
    const store = useChatStore.getState();
    const first = store.activeId;
    const file = new File(["hello"], "hello.txt");
    store.patchChat(first, { files: [file] });
    const second = store.newChat();
    store.patchChat(second, { files: [file] });
    store.chooseAgent(first, rag);
    expect(
      useChatStore.getState().conversations.find((c) => c.id === first)
    ).toMatchObject({
      agent: rag,
      files: [],
      notice: "Attachments removed. RAG Agent supports text only."
    });
    expect(
      useChatStore.getState().conversations.find((c) => c.id === second)?.files
    ).toEqual([file]);
  });
  it("ignores message callbacks for deleted conversations", () => {
    const store = useChatStore.getState();
    const deleted = store.activeId;
    store.deleteChat(deleted);
    store.updateMessage(deleted, "late", { content: "late" });
    store.appendMessage(deleted, {
      id: "late",
      role: "assistant",
      content: "late"
    });
    expect(useChatStore.getState().conversations[0].messages).toEqual([]);
  });
});
